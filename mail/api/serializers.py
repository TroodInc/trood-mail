import smtplib
from datetime import datetime

from django_mailbox.models import Mailbox
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from mail.api.models import Folder, Contact, Mail, \
    CustomMailbox


class EmailsListHeaderField(serializers.ListField):

    def to_internal_value(self, data):
        return ",".join(data)

    def to_representation(self, data):
        return data.split(",")


class FolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = ("id", "name", "mailbox", )


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ("id", "email", "name", "folder")


class BulkAssignSerializer(serializers.Serializer):
    contacts = serializers.ListField(serializers.IntegerField())

    class Meta:
        fields = ('contacts',)

    def to_internal_value(self, data):
        contact_ids = data.get('contacts')
        if not contact_ids:
            raise ValidationError({'contacts': 'Contacts is empty'})
        contacts = list(Contact.objects.in_bulk(contact_ids).values())
        internalized_data = data.copy()
        internalized_data['contacts'] = contacts
        return internalized_data


class MailSerializer(serializers.ModelSerializer):
    to = EmailsListHeaderField(source="to_header")
    bcc = EmailsListHeaderField(required=False)
    created_at = serializers.DateTimeField(source="processed", read_only=True)

    class Meta:
        model = Mail
        fields = (
            "id", "mailbox", "subject", "body", "to", "bcc", "encoded",  "from_address",
            "read", "outgoing", "in_reply_to", "replies", "folder", "attachments", "created_at")
        read_only_fields = (
            "id", "encoded",  "from_address", "outgoing", "in_reply_to", "replies", "attachments",
            "created_at",
        )

    def to_representation(self, instance):
        data = super(MailSerializer, self).to_representation(instance)
        data['mailbox'] = instance.mailbox.mailer.id

        body = instance.html or instance.text
        data['body'] = body

        return data

    def to_internal_value(self, data):
        if 'read' in data:
            data['read'] = datetime.now()

        mailbox = data.get('mailbox', None)
        if mailbox:
            data['mailbox'] = CustomMailbox.objects.get(pk=mailbox).inbox.id

        data = super(MailSerializer, self).to_internal_value(data)

        return data


class InboxSerializer(serializers.ModelSerializer):
    IMAP = 'imap'
    POP3 = 'pop3'

    TRANSPORT_TYPES = (
        (IMAP, "IMAP"),
        (POP3, "POP3"),
    )

    TLS = 'tls'
    SSL = 'ssl'

    SECURE_TYPES = (
        (TLS, "TLS"),
        (SSL, "SSL"),
    )

    imap_host = serializers.CharField(source="location")
    email = serializers.EmailField(source="from_email")
    password = serializers.CharField(write_only=True)
    imap_port = serializers.IntegerField(source="port")

    class Meta:
        model = Mailbox
        fields = ("name", "active", "email", "password", "imap_host", "imap_port", "last_polling")

    def to_internal_value(self, data):
        secure = data.pop("secure", "")
        data = super(InboxSerializer, self).to_internal_value(data)

        password = data.pop("password")
        host = data.pop("location")
        port = data.pop("port")

        if secure != "":
            secure = "+{}".format(secure)

        username = data["from_email"].split("@")[0]

        data['uri'] = "imap{}://{}:{}@{}:{}".format(secure, username, password, host, port)

        return data


class TroodMailboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomMailbox
        fields = ("id", "smtp_host", "smtp_port")

    def validate(self, data):
        validated_data = super().validate(data)
        server = smtplib.SMTP(validated_data['smtp_host'],
                              validated_data['smtp_port'])
        server.ehlo()
        server.starttls()
        try:
            server.login(validated_data['email'], validated_data['password'])
        except smtplib.SMTPAuthenticationError as e:
            error_message = f'SMTP server login error: invalid email or password '
            raise ValidationError(error_message)
        finally:
            server.quit()
        return data

    def to_representation(self, instance):
        data = super(TroodMailboxSerializer, self).to_representation(instance)
        data.update(InboxSerializer(instance.inbox).data)

        return data

    def to_internal_value(self, data):
        data["sender_settings"] = super(TroodMailboxSerializer, self).to_internal_value(data)
        inbox_serializer = InboxSerializer(data=data)
        inbox_serializer.is_valid(raise_exception=True)
        data["inbox_settings"] = inbox_serializer.validated_data

        return data

    def create(self, validated_data):
        inbox = Mailbox.objects.create(**validated_data["inbox_settings"])

        return CustomMailbox.objects.create(**validated_data["sender_settings"], inbox=inbox)


class MoveMailsToFolderSerializer(serializers.ModelSerializer):
    messages = serializers.ListField(child=serializers.IntegerField())

    class Meta:
        model = Folder
        fields = ('messages', )
