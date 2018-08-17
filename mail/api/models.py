import email
import gzip
import logging
import mimetypes
import re
import smtplib
import uuid
from email.encoders import encode_quopri, encode_base64
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email import encoders
from email import utils as email_utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, parsedate_to_datetime

import base64
import os
import six
import sys
from django.core.files.base import ContentFile
from django.db import models
from django_mailbox.models import Mailbox
from django.utils.translation import ugettext_lazy as _
from django_mailbox import utils


logger = logging.getLogger(__name__)


class ModelApiError(Exception):
    pass


class Inbox(Mailbox):
    class Meta:
        proxy = True

    def _get_dehydrated_message(self, msg, record):
        settings = utils.get_settings()

        new = EmailMessage()
        if msg.is_multipart():
            for header, value in msg.items():
                new[header] = value.replace('\n', '').replace('\r', '')
            for part in msg.get_payload():
                new.attach(
                    self._get_dehydrated_message(part, record)
                )
        elif (
            settings['strip_unallowed_mimetypes']
            and not msg.get_content_type() in settings['allowed_mimetypes']
        ):
            for header, value in msg.items():
                new[header] = value
            # Delete header, otherwise when attempting to  deserialize the
            # payload, it will be expecting a body for this.
            del new['Content-Transfer-Encoding']
            new[settings['altered_message_header']] = (
                'Stripped; Content type %s not allowed' % (
                    msg.get_content_type()
                )
            )
            new.set_payload('')
        elif (
            (
                msg.get_content_type() not in settings['text_stored_mimetypes']
            ) or
            ('attachment' in msg.get('Content-Disposition', ''))
        ):
            filename = None
            raw_filename = msg.get_filename()
            if raw_filename:
                filename = utils.convert_header_to_unicode(raw_filename)
            if not filename:
                extension = mimetypes.guess_extension(msg.get_content_type())
            else:
                _, extension = os.path.splitext(filename)
            if not extension:
                extension = '.bin'

            attachment = Attachment()

            attachment.document.save(
                uuid.uuid4().hex + extension,
                ContentFile(
                    six.BytesIO(
                        msg.get_payload(decode=True)
                    ).getvalue()
                )
            )
            attachment.message = record
            for key, value in msg.items():
                attachment[key] = value
            attachment.save()

            placeholder = EmailMessage()
            placeholder[
                settings['attachment_interpolation_header']
            ] = str(attachment.pk)
            new = placeholder
        else:
            content_charset = msg.get_content_charset()
            if not content_charset:
                content_charset = 'ascii'
            try:
                # Make sure that the payload can be properly decoded in the
                # defined charset, if it can't, let's mash some things
                # inside the payload :-\
                msg.get_payload(decode=True).decode(content_charset)
            except LookupError:
                logger.warning(
                    "Unknown encoding %s; interpreting as ASCII!", content_charset
                )
                msg.set_payload(
                    msg.get_payload(decode=True).decode('ascii', 'ignore')
                )
            except ValueError:
                logger.warning("Decoding error encountered; interpreting %s as ASCII!", content_charset)
                msg.set_payload(
                    msg.get_payload(decode=True).decode('ascii', 'ignore')
                )
            new = msg
        return new

    def _process_message(self, message):
        msg = Mail()
        settings = utils.get_settings()

        if settings['store_original_message']:
            self._process_save_original_message(message, msg)
        msg.mailbox = self

        if 'subject' in message:
            msg.subject = (
                utils.convert_header_to_unicode(message['subject'])[0:255]
            )
        if 'message-id' in message:
            msg.message_id = message['message-id'][0:255].strip()
        if 'from' in message:
            msg.from_header = utils.convert_header_to_unicode(message['from'])
        if 'to' in message:
            msg.to_header = utils.convert_header_to_unicode(message['to'])
        elif 'Delivered-To' in message:
            msg.to_header = utils.convert_header_to_unicode(
                message['Delivered-To']
            )

        if 'in-reply-to' in message:
            try:
                msg.in_reply_to = Mail.objects.filter(
                    message_id=message['in-reply-to'].strip()
                )[0]
            except IndexError:
                pass

        msg.save()
        message = self._get_dehydrated_message(message, msg)
        try:
            body = message.as_string()
        except KeyError as exc:
            logger.warning("Failed to parse message: %s", exc, )
            return None
        msg.set_body(body)

        if 'date' in message:
            msg.date = parsedate_to_datetime(message['date'])

        msg.save()
        return msg


class CustomMailbox(models.Model):
    TLS = 'tls'
    SSL = 'ssl'

    SECURE_TYPES = (
        (TLS, "TLS"),
        (SSL, "SSL"),
    )

    owner = models.IntegerField(_('Owner'), null=True, default=None)
    inbox = models.OneToOneField(Inbox, related_name="mailer", on_delete=models.CASCADE)
    smtp_host = models.CharField(max_length=128)
    smtp_port = models.IntegerField(default=465)
    smtp_secure = models.CharField(choices=SECURE_TYPES, max_length=4, default=SSL)
    shared = models.BooleanField(default=False)


class Chain(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)


# @todo: OPTIMIZZZZZEEEE !!!!!!!
class Mail(models.Model):
    bcc = models.TextField(null=True)
    draft = models.BooleanField(default=False)
    chain = models.ForeignKey(Chain, null=True, on_delete=models.SET_NULL)

    mailbox = models.ForeignKey(
        'django_mailbox.Mailbox', verbose_name=_(u'Mailbox'), on_delete=models.SET_NULL, null=True
    )

    subject = models.CharField(_(u'Subject'), max_length=255, blank=True, null=True)
    message_id = models.CharField(_(u'Message ID'), max_length=255, blank=True, null=True)

    in_reply_to = models.ForeignKey(
        'Mail', related_name='mail_replies', blank=True,
        null=True, verbose_name=_(u'In reply to'), on_delete=models.SET_NULL
    )

    from_header = models.CharField(_('From header'), max_length=255, blank=True, default="")
    to_header = models.TextField(_(u'To header'), blank=True, default="")
    outgoing = models.BooleanField(_(u'Outgoing'), default=False)
    body = models.TextField(_(u'Body'), blank=True, default="")
    encoded = models.BooleanField(
        _(u'Encoded'), default=False, help_text=_('True if the e-mail body is Base64 encoded'),
    )
    date = models.DateTimeField(_('Date'), auto_now_add=True, blank=True, null=True)
    processed = models.DateTimeField(_('Processed'), auto_now_add=True)
    read = models.DateTimeField(_(u'Read'), default=None, blank=True, null=True,)
    is_read = models.BooleanField(default=False)

    eml = models.FileField(
        _(u'Raw message contents'), null=True, upload_to="messages", help_text=_(u'Original full content of message')
    )

    objects = models.Manager()

    @property
    def address(self) -> list:
        addresses = self.to_addresses + self.from_address
        return addresses

    @property
    def from_address(self) -> list:
        if self.from_header:
            return [parseaddr(self.from_header)[1].lower()]
        else:
            return []

    @property
    def to_addresses(self) -> list:
        """Returns a list of addresses to which this message was sent."""
        addresses = []
        for address in self.to_header.split(','):
            if address:
                addresses.append(
                    parseaddr(
                        address
                    )[1].lower()
                )
        return addresses

    @property
    def text(self):
        """
        Returns the message body matching content type 'text/plain'.
        """
        return utils.get_body_from_message(
            self.get_email_object(), 'text', 'plain'
        ).replace('=\n', '').strip()

    @property
    def html(self):
        """
        Returns the message body matching content type 'text/html'.
        """
        return utils.get_body_from_message(
            self.get_email_object(), 'text', 'html'
        ).replace('\n', '').strip()

    def _rehydrate(self, msg):
        new = EmailMessage()
        settings = utils.get_settings()

        if msg.is_multipart():
            for header, value in msg.items():
                new[header] = value.replace('\n', '').replace('\r', '')
            for part in msg.get_payload():
                new.attach(
                    self._rehydrate(part)
                )
        elif settings['attachment_interpolation_header'] in msg.keys():
            try:
                attachment = Attachment.objects.get(
                    pk=msg[settings['attachment_interpolation_header']]
                )
                for header, value in attachment.items():
                    new[header] = value.replace('\n', '').replace('\r', '')
                encoding = new['Content-Transfer-Encoding']
                if encoding and encoding.lower() == 'quoted-printable':
                    # Cannot use `email.encoders.encode_quopri due to
                    # bug 14360: http://bugs.python.org/issue14360
                    output = six.BytesIO()
                    encode_quopri(
                        six.BytesIO(
                            attachment.document.read()
                        ),
                        output,
                        quotetabs=True,
                        header=False,
                    )
                    new.set_payload(
                        output.getvalue().decode().replace(' ', '=20')
                    )
                    del new['Content-Transfer-Encoding']
                    new['Content-Transfer-Encoding'] = 'quoted-printable'
                else:
                    new.set_payload(
                        attachment.document.read()
                    )
                    del new['Content-Transfer-Encoding']
                    encode_base64(new)
            except Attachment.DoesNotExist:
                new[settings['altered_message_header']] = (
                        'Missing; Attachment %s not found' % (
                    msg[settings['attachment_interpolation_header']]
                )
                )
                new.set_payload('')
        else:
            for header, value in msg.items():
                new[header] = value.replace('\r', '').replace('\n', '')
            new.set_payload(
                msg.get_payload()
            )
        return new

    def get_body(self):
        if self.encoded:
            return base64.b64decode(self.body.encode('ascii'))
        return self.body.encode('utf-8')

    def set_body(self, body):
        """Set the `body` field of this record.

        This will automatically base64-encode the message contents to
        circumvent a limitation in earlier versions of Django in which
        no fields existed for storing arbitrary bytes.

        """
        if six.PY3:
            body = body.encode('utf-8')
        self.encoded = True
        self.body = base64.b64encode(body).decode('ascii')

    def get_email_object(self):
        """Returns an `email.message.Message` instance representing the
        contents of this message and all attachments.

        See [email.Message.Message]_ for more information as to what methods
        and properties are available on `email.message.Message` instances.

        .. note::

           Depending upon the storage methods in use (specifically --
           whether ``DJANGO_MAILBOX_STORE_ORIGINAL_MESSAGE`` is set
           to ``True``, this may either create a "rehydrated" message
           using stored attachments, or read the message contents stored
           on-disk.

        .. [email.Message.Message]: Python's `email.message.Message` docs
           (https://docs.python.org/2/library/email.message.html)

        """
        if self.eml:
            if self.eml.name.endswith('.gz'):
                body = gzip.GzipFile(fileobj=self.eml).read()
            else:
                self.eml.open()
                body = self.eml.file.read()
                self.eml.close()
        else:
            body = self.get_body()
        if six.PY3:
            flat = email.message_from_bytes(body)
        else:
            flat = email.message_from_string(body)
        return self._rehydrate(flat)

    def delete(self, *args, **kwargs):
        """Delete this message and all stored attachments."""
        for attachment in self.attachments.all():
            # This attachment is attached only to this message.
            attachment.delete()
        return super(Mail, self).delete(*args, **kwargs)

    def __str__(self):
        return self.subject

    class Meta:
        verbose_name = _('E-mail message')
        verbose_name_plural = _('E-mail messages')
        ordering = ['-processed']

    def send(self):
        msg = self.get_email_object()

        for attachment in self.attachments.all():
            meta = attachment.document.file.meta

            file = MIMEBase(*attachment.document.file.type.split('/'), filename=meta['filename'])
            file.set_payload(attachment.document.file.read())
            encoders.encode_base64(file)

            file.add_header('Content-Disposition', 'attachment; filename="{}"'.format(meta['filename']))
            file.add_header('Content-ID', '<{}>'.format(meta['id']))
            file.add_header('X-Attachment-Id', meta['id'])
            msg.attach(file)

        if self.mailbox.mailer.smtp_secure == "ssl":
            server = smtplib.SMTP_SSL(self.mailbox.mailer.smtp_host, self.mailbox.mailer.smtp_port)
        else:
            server = smtplib.SMTP(self.mailbox.mailer.smtp_host, self.mailbox.mailer.smtp_port)
            server.starttls()

        server.login(self.mailbox.from_email, self.mailbox.password)
        server.send_message(msg=msg)
        server.quit()

        self.outgoing = True
        self.save()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if self.pk is None and self.outgoing:
            self.from_header = self.mailbox.from_email
            self.message_id = email_utils.make_msgid()

            msg = MIMEMultipart()
            msg["Subject"] = self.subject
            msg["From"] = self.from_header
            msg["To"] = self.to_header
            msg["Bcc"] = self.bcc
            msg['Message-ID'] = self.message_id

            if self.in_reply_to:
                msg["In-Reply-To"] = self.in_reply_to.message_id

            msg.attach(MIMEText(self.body, "html"))

            self.set_body(
                msg.as_string()
            )

        if self.in_reply_to:
            self.chain = self.in_reply_to.chain

        else:
            self.chain = Chain.objects.create()

        super(Mail, self).save()


class Folder(models.Model):
    owner = models.IntegerField(_('Owner'), null=True, default=None)
    name = models.CharField(max_length=128, null=False)
    chains = models.ManyToManyField(Chain, related_name="folders")

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name}'


class Attachment(models.Model):
    message = models.ForeignKey(
        Mail, related_name='attachments', null=True, blank=True, verbose_name=_('Message'), on_delete=models.CASCADE
    )

    headers = models.TextField(_(u'Headers'), null=True, blank=True,)
    document = models.FileField(_(u'Document'), upload_to=utils.get_attachment_save_path, )

    def delete(self, *args, **kwargs):
        """Deletes the attachment."""
        self.document.delete()
        return super(Attachment, self).delete(*args, **kwargs)

    def _get_rehydrated_headers(self):
        headers = self.headers
        if headers is None:
            return EmailMessage()
        if sys.version_info < (3, 0):
            try:
                headers = headers.encode('utf-8')
            except UnicodeDecodeError:
                headers = headers.decode('utf-8').encode('utf-8')
        return email.message_from_string(headers)

    def _set_dehydrated_headers(self, email_object):
        self.headers = email_object.as_string()

    def __delitem__(self, name):
        rehydrated = self._get_rehydrated_headers()
        del rehydrated[name]
        self._set_dehydrated_headers(rehydrated)

    def __setitem__(self, name, value):
        rehydrated = self._get_rehydrated_headers()
        rehydrated[name] = re.sub("\r\n", "", value)
        self._set_dehydrated_headers(rehydrated)

    def get_filename(self):
        """Returns the original filename of this attachment."""
        file_name = self._get_rehydrated_headers().get_filename()
        if isinstance(file_name, six.string_types):
            result = utils.convert_header_to_unicode(file_name)
            if result is None:
                return file_name
            return result
        else:
            return None

    def items(self):
        return self._get_rehydrated_headers().items()

    def __getitem__(self, name):
        value = self._get_rehydrated_headers()[name]
        if value is None:
            raise KeyError('Header %s does not exist' % name)
        return value

    def __str__(self):
        return self.document.url

    class Meta:
        verbose_name = _('Message attachment')
        verbose_name_plural = _('Message attachments')


class Contact(models.Model):
    folder = models.ForeignKey(Folder, null=True, on_delete=models.SET_NULL)
    email = models.EmailField(blank=False, null=True, default=None, unique=True)
    name = models.CharField(max_length=128, null=True)

    class Meta:
        ordering = ['name']

    def assign_to(self, folder=None):
        if self.folder:
            if folder is None:
                self.folder = None
                self.save()
            else:
                error_message = f'Contact {self.id} already assigned ' \
                                f'to folder {self.folder}'
                raise ModelApiError(error_message)
        else:
            self.folder = folder
            self.save()
