import smtplib
from datetime import datetime
from urllib.parse import urlparse, urlencode, quote_plus

from django.core.files.storage import default_storage
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.validators import UniqueValidator


from mail.api.models import Folder, Contact, Mail, \
    Mailbox, Attachment, Template


class EmailsListHeaderField(serializers.ListField):

    def to_internal_value(self, data):
        return ",".join(data)

    def to_representation(self, data):
        return data.split(",")


class FolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = ("id", "name", "owner",)


class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = ("id", "name", "owner", "alias", "subject", "body")


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


class AttachmentsSerializer(serializers.ModelSerializer):
    # @todo: Fix to deal with default filestorage not only TroodFile

    class Meta:
        model = Attachment
        fields = '__all__'

    def to_representation(self, instance):
        if instance.document:
            return instance.document.file.meta
        else:
            return None


class MailSerializer(serializers.ModelSerializer):
    to = EmailsListHeaderField(source="to_header")
    bcc = EmailsListHeaderField(required=False)
    created_at = serializers.DateTimeField(source="date", read_only=True)
    attachments = AttachmentsSerializer(many=True, required=False)
    read_date = serializers.DateTimeField(source="read", read_only=True)

    class Meta:
        model = Mail
        fields = (
            "id", "mailbox", "subject", "body", "to", "bcc", "encoded",  "from_address", "is_read",
            "read_date", "outgoing", "in_reply_to", "mail_replies", "attachments", "created_at",
            "message_id", "chain", "draft"
        )
        read_only_fields = (
            "id", "encoded",  "from_address", "outgoing", "mail_replies",
            "created_at", "message_id", "chain", "read_date"
        )

    def to_representation(self, instance):
        data = super(MailSerializer, self).to_representation(instance)

        body = instance.html or instance.text
        data['body'] = body

        return data

    def to_internal_value(self, data):

        attachments = data.pop("attachments", [])

        data = super(MailSerializer, self).to_internal_value(data)

        data['attachments'] = attachments

        if 'is_read' in data:
            if data['is_read']:
                data['read'] = datetime.now()
            else:
                data['read'] = None

        return data

    def create(self, validated_data):
        attachments = validated_data.pop("attachments", [])
        instance = super(MailSerializer, self).create(validated_data)

        for attachment in attachments:
            obj = Attachment.objects.create(message=instance)
            obj.document.save(attachment, default_storage.open(attachment), save=True)

        return instance

    def update(self, instance, validated_data):
        validated_data.pop("attachments", [])

        return super(MailSerializer, self).update(instance, validated_data)


class TroodMailboxSerializer(serializers.ModelSerializer):
    IMAP = 'imap'
    POP3 = 'pop3'

    TRANSPORT_TYPES = (
        (IMAP, "IMAP"),
        (POP3, "POP3"),
    )

    imap_host = serializers.CharField(source="location")
    email = serializers.EmailField(source="from_email", validators=[UniqueValidator(Mailbox.objects.all())])
    password = serializers.CharField(write_only=True)
    imap_port = serializers.IntegerField(source="port", max_value=64535)
    smtp_port = serializers.IntegerField(max_value=64535)

    class Meta:
        model = Mailbox
        fields = (
            "id", "smtp_host", "smtp_port", "smtp_secure", "owner", "shared",  "name",
            "active", "password", "email", "imap_host", "imap_port", "last_polling", "custom_query",
        )

        read_only_fields = ("owner", "id")

    def to_internal_value(self, data):
        imap_secure = data.pop("imap_secure", None)

        if imap_secure:
            imap_secure = "+{}".format(imap_secure)
        elif self.instance:
            parts = urlparse(self.instance.uri).scheme.lower().split('+')
            if len(parts) == 2:
                imap_secure = "+{}".format(parts[1])
        else:
            imap_secure = ""

        data = super(TroodMailboxSerializer, self).to_internal_value(data)

        password = data.get("password", getattr(self.instance, "password", None))
        host = data.pop("location", getattr(self.instance, "location", None))
        port = data.pop("port", getattr(self.instance, "port", None))
        email = data.get("from_email", getattr(self.instance, "from_email", None))

        data['uri'] = "imap{}://{}:{}@{}:{}".format(imap_secure, quote_plus(email), quote_plus(password), host, port)

        return data

    def validate(self, data):
        validated_data = super().validate(data)

        if 'smtp_host' in validated_data \
                or 'smtp_port' in validated_data \
                or 'from_email' in validated_data \
                or 'password' in validated_data \
                or 'smtp_secure' in validated_data:

            secure = self._get_or_from_instance('smtp_secure', validated_data, self.instance)
            host = self._get_or_from_instance('smtp_host', validated_data, self.instance)
            port = self._get_or_from_instance('smtp_port', validated_data, self.instance)

            try:
                if secure == 'ssl':
                    server = smtplib.SMTP_SSL(host, port, timeout=5)
                elif secure == 'tls':
                    server = smtplib.SMTP(host, port, timeout=5)
                    server.starttls()
                else:
                    server = smtplib.SMTP(host, port, timeout=5)

                email = validated_data.get('from_email', getattr(self.instance, 'from_email', ""))
                password = validated_data.pop('password', getattr(self.instance, 'password', ""))

                server.login(email, password)
                server.quit()
            except smtplib.SMTPAuthenticationError as e:
                error_message = f'SMTP server login error: invalid email or password'
                raise ValidationError(error_message)
            except Exception as e:
                raise ValidationError(f'Smtp Connection settings wrong: {e}')

        return validated_data

    def to_representation(self, instance):
        data = super(TroodMailboxSerializer, self).to_representation(instance)
        schema = instance._protocol_info.scheme.lower()

        parts = schema.split('+')
        if len(parts) == 2:
            data['imap_secure'] = parts[1]
        else:
            data['imap_secure'] = None

        return data

    def _get_or_from_instance(self, key, data, instance):
        if key in data:
            return data[key]
        elif instance:
            return getattr(instance, key)
        else:
            raise AttributeError(f'Attr {key} doesnt exist')


class MoveMailsToFolderSerializer(serializers.ModelSerializer):
    messages = serializers.ListField(child=serializers.IntegerField())

    class Meta:
        model = Folder
        fields = ('messages', )
