from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import detail_route, list_route
from rest_framework.exceptions import ValidationError, ParseError
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from mail.api.models import Folder, Contact, \
    ModelApiError, Mail, CustomMailbox
from mail.api.serializers import MailSerializer, \
    FolderSerializer, ContactSerializer, MoveMailsToFolderSerializer, \
    BulkAssignSerializer, TroodMailboxSerializer


class MailboxViewSet(viewsets.ModelViewSet):
    queryset = CustomMailbox.objects.all()
    serializer_class = TroodMailboxSerializer
    # permission_classes = (IsAuthenticated, )

    @detail_route(methods=["POST"])
    def fetch(self, request, pk=None):
        mailbox = self.get_object()

        print(mailbox.inbox.uri)

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
        for mailbox in queryset.filter(actile=True):
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


class MailViewSet(viewsets.ModelViewSet):
    queryset = Mail.objects.all()
    serializer_class = MailSerializer
    # permission_classes = (IsAuthenticated, )

    def perform_create(self, serializer):
        mail = serializer.save()

        if not mail.draft:
            mail.send()


class FolderViewSet(viewsets.ModelViewSet):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer
    # permission_classes = (IsAuthenticated, )

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


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    # permission_classes = (IsAuthenticated, )

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