from django_mailbox.models import Mailbox, Message
from rest_framework import viewsets
from rest_framework.decorators import detail_route, list_route
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mail.api.models import Folder, Contact
from mail.api.serializers import MailboxSerializer, MailSerializer, FolderSerializer, ContactSerializer


class MailboxViewSet(viewsets.ModelViewSet):
    queryset = Mailbox.objects.all()
    serializer_class = MailboxSerializer
    # permission_classes = (IsAuthenticated, )

    @detail_route(methods=["POST"])
    def fetch(self, request, pk=None):
        mailbox = self.get_object()
        mails, new_contacts = self._fetch_mailbox(mailbox)

        return Response({
            "status": "OK",
            "data": {
                "mails received": len(mails),
                "contacts added": new_contacts
            }
        })

    @list_route(methods=["POST"])
    def fetchall(self, request):
        queryset = self.get_queryset()

        mails_total = contast_total = 0
        for mailbox in queryset.filter(actile=True):
            mails, new_contacts = self._fetch_mailbox(mailbox)
            mails_total += len(mails)
            contast_total += new_contacts

        return Response({
            "status": "OK",
            "data": {
                "mails received": mails_total,
                "contacts added": contast_total
            }
        })

    def _fetch_mailbox(self, mailbox):
        mails = mailbox.get_new_mail()

        new_contacts = 0
        for mail in mails:
            for address in mail.address:
                c, created = Contact.objects.get_or_create(email=address)
                if created:
                    new_contacts += 1

        return mails, new_contacts


class MailViewSet(viewsets.ModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MailSerializer
    # permission_classes = (IsAuthenticated, )

    def create(self, request, *args, **kwargs):
        pass


class FolderViewSet(viewsets.ModelViewSet):
    queryset = Folder.objects.all()
    serializer_class = FolderSerializer
    # permission_classes = (IsAuthenticated, )


class ContactViewSet(viewsets.ModelViewSet):
    queryset = Contact.objects.all()
    serializer_class = ContactSerializer
    # permission_classes = (IsAuthenticated, )
