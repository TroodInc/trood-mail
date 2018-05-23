from datetime import datetime
from django_mailbox.models import Mailbox, Message
from rest_framework import serializers

from mail.api.models import Folder, Contact


class FolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = ("id", "name", "mailbox")


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ("id", "email", "name", )


class NewMailSerializer(serializers.Serializer):
    pass


class MailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = (
            "id", "mailbox", "subject", "body", "encoded",  "from_address", "to_addresses",
            "read", "outgoing", "in_reply_to", "replies", "folder", "attachments")
        read_only_fields = (
            "id", "mailbox", "subject", "body", "encoded",  "from_address", "to_addresses",
            "outgoing", "in_reply_to", "replies", "attachments"
        )

    def to_representation(self, instance):
        res = super(MailSerializer, self).to_representation(instance)
        res["folder"] = None if not len(res["folder"]) else res["folder"][0]

        return res

    def to_internal_value(self, data):
        read = data.get("read", None)
        data["folder"] = [data["folder"]]

        if read:
            data['read'] = datetime.now()

        return super(MailSerializer, self).to_internal_value(data)


class MailboxSerializer(serializers.ModelSerializer):
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

    host = serializers.CharField(source="location")
    email = serializers.EmailField(source="from_email")
    password = serializers.CharField(write_only=True)
    port = serializers.IntegerField()
    type = serializers.ChoiceField(choices=TRANSPORT_TYPES)

    class Meta:
        model = Mailbox
        fields = ("id", "name", "active", "email", "password", "host", "port", "type", "last_polling")

    def to_internal_value(self, data):
        secure = data.pop("secure", "")
        data = super(MailboxSerializer, self).to_internal_value(data)

        password = data.pop("password")
        host = data.pop("location")
        port = data.pop("port")
        transport = data.pop("type")

        if secure != "":
            secure = "+{}".format(secure)

        username = data["from_email"].split("@")[0]

        data['uri'] = "{}{}://{}:{}@{}:{}".format(transport, secure, username, password, host, port)

        return data
