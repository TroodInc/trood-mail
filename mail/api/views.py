import itertools
from django.db import transaction
from django.db.models import Count, Q, Max, Min, OuterRef, Subquery
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters
from rest_framework.decorators import detail_route, list_route
from rest_framework.exceptions import ValidationError, ParseError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.viewsets import ReadOnlyModelViewSet

from mail.api.filters import MailsFilter
from mail.api.models import Folder, Contact, ModelApiError, Mail, CustomMailbox
from mail.api.pagination import PageNumberPagination
from mail.api.serializers import MailSerializer, \
    FolderSerializer, ContactSerializer, MoveMailsToFolderSerializer, \
    BulkAssignSerializer, TroodMailboxSerializer


class MailboxViewSet(viewsets.ModelViewSet):
    queryset = CustomMailbox.objects.all()
    serializer_class = TroodMailboxSerializer

    permission_classes = (IsAuthenticated, )

    @detail_route(methods=["POST"])
    def fetch(self, request, pk=None):
        mailbox = self.get_object()

        mails, new_contacts = self._fetch_mailbox(mailbox.inbox)

        data = {
            "mails received": len(mails),
            "contacts added": new_contacts
        }

        return Response(data, status=HTTP_200_OK)

    @list_route(methods=["POST"])
    def fetchall(self, request):
        queryset = self.get_queryset()

        mails_total = contast_total = 0
        for mailbox in queryset.filter(inbox__active=True):
            mails, new_contacts = self._fetch_mailbox(mailbox.inbox)
            mails_total += len(mails)
            contast_total += new_contacts

        data = {
            "mails received": mails_total,
            "contacts added": contast_total
        }

        return Response(data, status=HTTP_200_OK)

    def _fetch_mailbox(self, mailbox):
        mails = mailbox.get_new_mail()

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

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user.id)


class MailViewSet(viewsets.ModelViewSet):
    queryset = Mail.objects.all()
    serializer_class = MailSerializer
    pagination_class = PageNumberPagination
    filter_backends = (DjangoFilterBackend, filters.SearchFilter,)
    search_fields = ('subject', 'bcc', 'from_header', 'to_header', )
    filter_class = MailsFilter

    permission_classes = (IsAuthenticated, )

    def perform_create(self, serializer):
        mail = serializer.save(outgoing=True)

        for address in mail.address:
            Contact.objects.get_or_create(email=address)

        if not mail.draft:
            mail.send()


class ChainViewSet(ReadOnlyModelViewSet):
    pagination_class = PageNumberPagination
    permission_classes = (IsAuthenticated,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    search_fields = ('subject', 'bcc', 'from_header', 'to_header',)
    ordering_fields = ('last', 'first', 'processed')

    def get_queryset(self):
        q_total = Count("pk")
        q_unread = Count("pk", filter=Q(read=None))
        q_subj = Mail.objects.filter(chain=OuterRef('chain')).order_by("processed")[:1]

        queryset = Mail.objects.values("chain").order_by("chain").distinct().annotate(
            total=q_total, unread=q_unread,
            last=Max("processed"), first=Min("processed"),
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
                    'contacts': self._get_chain_contacts(chain['chain'])
                })

        return self.get_paginated_response(result)

    def _get_chain_contacts(self, chain):
        mails = Mail.objects.filter(chain=chain)
        addresses = [mail.address for mail in mails]
        contacts = set(itertools.chain(*addresses))

        return contacts


class FolderViewSet(viewsets.ModelViewSet):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer
    permission_classes = (IsAuthenticated, )

    @detail_route(methods=['POST'], url_path='bulk-move')
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

    @detail_route(methods=['PATCH'], url_path='bulk-assign')
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

    @detail_route(methods=['PATCH'], url_path='bulk-unassign')
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
    filter_backends = (DjangoFilterBackend, filters.SearchFilter,)
    search_fields = ('email', 'name')
    permission_classes = (IsAuthenticated, )

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