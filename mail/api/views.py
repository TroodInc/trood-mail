import itertools

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count, Q, Max, Min, OuterRef, Subquery, F
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, ParseError
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED

from mail.api.filters import ChainsFilter
from mail.api.models import Folder, Contact, ModelApiError, Mail, CustomMailbox, Chain, Template
from mail.api.pagination import PageNumberPagination
from mail.api.serializers import MailSerializer, \
    FolderSerializer, ContactSerializer, MoveMailsToFolderSerializer, \
    BulkAssignSerializer, TroodMailboxSerializer, InboxSerializer, TemplateSerializer
from mail.api.utils import mail_fetching_filter


class MailboxViewSet(viewsets.ModelViewSet):
    queryset = CustomMailbox.objects.all()
    serializer_class = TroodMailboxSerializer

    @action(detail=True, methods=["POST"])
    def fetch(self, request, pk=None):
        mailbox = self.get_object()

        mails, new_contacts = self._fetch_mailbox(mailbox.inbox)

        data = {
            "mails_received": len(mails),
            "contacts_added": new_contacts
        }

        return Response(data, status=HTTP_200_OK)

    @action(detail=False, methods=["POST"])
    def fetchall(self, request):
        queryset = self.get_queryset()

        mails_total = contast_total = 0
        failed = []
        for mailbox in queryset.filter(inbox__active=True):

            try:
                mails, new_contacts = self._fetch_mailbox(mailbox.inbox)
                mails_total += len(mails)
                contast_total += new_contacts
            except Exception as e:
                failed.append({
                    "mailbox": mailbox.id,
                    "error": str(e)
                })

        data = {
            "mails_received": mails_total,
            "contact_added": contast_total,
            "fails": failed
        }

        return Response(data, status=HTTP_200_OK)

    def _fetch_mailbox(self, mailbox):
        mails = mailbox.get_new_mail(mail_fetching_filter)

        new_contacts = 0
        for mail in mails:
            for address in mail.address:
                contact, created = Contact.objects.get_or_create(email=address)
                mail, contact = \
                    self._move_mail_to_folder_assigned_to(mail, contact)
                if created:
                    new_contacts += 1

        return mails, new_contacts

    def _move_mail_to_folder_assigned_to(self, mail, contact):
        try:
            folder = contact.folder
            folder.messages.add(mail)
            folder.save()
        except Exception:
            # TODO Log here
            pass
        finally:
            return mail, contact

    def create(self, request, *args, **kwargs):
        inbox = InboxSerializer(data=request.data)
        inbox.is_valid(raise_exception=True)
        inbox.save()

        mailbox = TroodMailboxSerializer(data=request.data)
        mailbox.is_valid(raise_exception=True)
        mailbox.save(owner=self.request.user.id, inbox=inbox.instance)

        return Response(mailbox.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        inbox = InboxSerializer(instance.inbox, data=request.data, partial=True)
        inbox.is_valid(raise_exception=True)
        inbox.save()

        mailbox = TroodMailboxSerializer(instance, data=request.data, partial=True)
        mailbox.is_valid(raise_exception=True)
        mailbox.save()

        return Response(mailbox.data)


class MailViewSet(viewsets.ModelViewSet):
    queryset = Mail.objects.all()
    serializer_class = MailSerializer
    pagination_class = PageNumberPagination
    search_fields = ('subject', 'bcc', 'from_header', 'to_header', )
    filter_fields = ('chain', 'outgoing')

    @action(detail=False, methods=["POST"])
    def from_template(self, request):
        template = request.data.pop("template", None)
        template = get_object_or_404(Template.objects.all(), alias=template)

        rendered = template.render(request.data.pop("data", None))

        request.data.update(rendered)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        return Response(serializer.data, HTTP_201_CREATED)

    def perform_create(self, serializer):
        mail = serializer.save(outgoing=True)

        for address in mail.address:
            Contact.objects.get_or_create(email=address)

        if not mail.draft:
            mail.send()


class ChainViewSet(viewsets.ModelViewSet):
    pagination_class = PageNumberPagination
    search_fields = ('mail__subject', 'mail__bcc', 'mail__from_header', 'mail__to_header',)
    ordering_fields = ('last', 'first', 'mail__date')
    filter_class = ChainsFilter

    def get_object(self):
        queryset = Chain.objects.all()
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        assert lookup_url_kwarg in self.kwargs, (
                'Expected view %s to be called with a URL keyword argument '
                'named "%s". Fix your URL conf, or set the `.lookup_field` '
                'attribute on the view correctly.' %
                (self.__class__.__name__, lookup_url_kwarg)
        )

        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        obj = get_object_or_404(queryset, **filter_kwargs)

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)

        return obj

    def get_queryset(self):
        q_total = Count("mail__pk")
        q_unread = Count("mail__pk", filter=Q(mail__read=None))
        q_received = Count("mail__pk", filter=Q(mail__outgoing=False))
        q_sent = Count("mail__pk", filter=Q(mail__outgoing=True))
        q_subj = Mail.objects.filter(chain=OuterRef('id')).order_by("date")[:1]

        queryset = Chain.objects.values("id").order_by("id").distinct().annotate(
            chain=F("id"),
            total=q_total, unread=q_unread, received=q_received, sent=q_sent,
            last=Max("mail__date"), first=Min("mail__date"),
            chain_subject=Subquery(q_subj.values("subject")),
        )

        return queryset

    def retrieve(self, request, pk):
        queryset = self.filter_queryset(self.get_queryset())
        chain = get_object_or_404(queryset, chain=pk)

        result = {
            **chain,
            'contacts': self._get_chain_contacts(pk)
        }

        return Response(result)

    def list(self, request):
        queryset = self.get_queryset()
        queryset = self.filter_queryset(queryset)

        page = self.paginate_queryset(queryset)

        result = []
        if page is not None:
            for chain in page:
                result.append({
                    **chain,
                    'contacts': self._get_chain_contacts(chain['id'])
                })

        return self.get_paginated_response(result)

    def update(self, request, *args, **kwargs):
        folder_id = request.data.pop("folder", None)
        chain = self.get_object()

        if folder_id:
            existing = chain.folders.filter(owner=request.user.id)
            chain.folders.remove(*existing)
            if folder_id != 'inbox':
                try:
                    folder = Folder.objects.get(id=folder_id, owner=request.user.id)
                    chain.folders.add(folder)

                except ObjectDoesNotExist:
                    raise ValidationError("You cant move to <folder: {}>".format(folder_id))

        return Response(status=HTTP_200_OK)

    def _get_chain_contacts(self, chain):
        mails = Mail.objects.filter(chain=chain)
        addresses = [mail.address for mail in mails]
        contacts = set(itertools.chain(*addresses))

        return contacts


class FolderViewSet(viewsets.ModelViewSet):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer

    @action(detail=True, methods=['POST'], url_path='bulk-move')
    def bulk_move(self, request, *args, **kwargs):
        folder = self.get_object()
        serializer = MoveMailsToFolderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message_ids = serializer.validated_data['messages']
        existing_message_ids = set(folder.messages.values_list('id', flat=True))
        movable_message_ids = set(message_ids)
        moved_message_ids = list(
            movable_message_ids.difference(existing_message_ids))

        if moved_message_ids:
            try:
                with transaction.atomic():
                    for message_id in moved_message_ids:
                        message = Mail.objects.get(id=message_id)
                        message.folder = folder
                        message.save()

            except Mail.DoesNotExist as e:
                    raise ValidationError(f'There is a problem to move '
                                          f'messages {moved_message_ids} '
                                          f'to folder {folder.id}')

        data = dict(serializer.data)
        data.update({'moved_messages': moved_message_ids})

        return Response(data, status=HTTP_200_OK)

    @action(detail=True, methods=['PATCH'], url_path='bulk-assign')
    def bulk_assign(self, request, *args, **kwargs):
        folder = self.get_object()
        serializer = BulkAssignSerializer(data=request.data, partial=True)
        serializer.is_valid()
        contacts = serializer.validated_data['contacts']
        for contact in contacts:
            try:
                with transaction.atomic():
                    contact.assign_to(folder=folder)
            except ModelApiError as e:
                raise ParseError(detail=str(e))
        return Response(ContactSerializer(contacts, many=True).data,
                        status=HTTP_200_OK)

    @action(detail=True, methods=['PATCH'], url_path='bulk-unassign')
    def bulk_unassign(self, request, *args, **kwargs):
        serializer = BulkAssignSerializer(data=request.data, partial=True)
        serializer.is_valid()
        contacts = serializer.validated_data['contacts']
        for contact in contacts:
            try:
                with transaction.atomic():
                    contact.assign_to(folder=None)
            except ModelApiError as e:
                raise ParseError(detail=str(e))
        return Response(ContactSerializer(contacts, many=True).data,
                        status=HTTP_200_OK)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user.id)


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    search_fields = ('email', 'name')

    def update(self, request, *args, **kwargs):
        contact = self.get_object()

        serializer = ContactSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        folder = serializer.validated_data.get('folder')
        try:
            with transaction.atomic():
                contact.assign_to(folder=folder)
        except ModelApiError as e:
            raise ParseError(detail=str(e))

        response_data = ContactSerializer(instance=contact).data

        return Response(response_data, status=HTTP_200_OK)


class TemplateViewSet(viewsets.ModelViewSet):
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user.id)