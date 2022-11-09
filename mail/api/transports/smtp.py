import smtplib
from email import encoders
from importlib._common import _

from django.db import models
from email.mime.base import MIMEBase
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import Serializer

from mail.api.transports.base import EmailTransport


class SMTPConfigSerializer(Serializer):
    TLS = 'tls'
    SSL = 'ssl'

    SECURE_TYPES = (
        (TLS, "TLS"),
        (SSL, "SSL"),
    )

    smtp_host = models.CharField(max_length=128)
    smtp_port = models.IntegerField(default=465)
    smtp_secure = models.CharField(choices=SECURE_TYPES, max_length=4, null=True, default=SSL)
    from_email = models.CharField(
        _(u'From email'), max_length=255, blank=True, null=True, default=None, unique=True,
        help_text=(_(
            "Example: MailBot &lt;mailbot@yourdomain.com&gt;<br />"
            "'From' header to set for outgoing email.<br />"
            "<br />"
            "If you do not use this e-mail inbox for outgoing mail, this "
            "setting is unnecessary.<br />"
            "If you send e-mail without setting this, your 'From' header will'"
            "be set to match the setting `DEFAULT_FROM_EMAIL`."
        )),

    )

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


class SMTPTransport(EmailTransport):
    name = "smtp"
    title = "SMTP"

    config_class = SMTPConfigSerializer

    def send(self, message):
        msg = message.get_email_object()

        for attachment in msg.attachments.all():
            meta = attachment.document.file.meta

            file = MIMEBase(*attachment.document.file.type.split('/'), filename=meta['filename'])
            file.set_payload(attachment.document.file.read())
            encoders.encode_base64(file)

            file.add_header('Content-Disposition', 'attachment; filename="{}"'.format(meta['filename']))
            file.add_header('Content-ID', '<{}>'.format(meta['id']))
            file.add_header('X-Attachment-Id', meta['id'])
            msg.attach(file)

        if message.mailbox.smtp_secure == "ssl":
            server = smtplib.SMTP_SSL(message.mailbox.smtp_host, message.mailbox.smtp_port)
        elif message.mailbox.smtp_secure == "tls":
            server = smtplib.SMTP(message.mailbox.smtp_host, message.mailbox.smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP(message.mailbox.smtp_host, message.mailbox.smtp_port)

        server.login(message.mailbox.from_email, message.mailbox.password)
        server.send_message(msg=msg)
        server.quit()
