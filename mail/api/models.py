import logging
import smtplib
import email
import gzip
import six

from django.db import models
from django_mailbox.models import Mailbox, Message
from django.utils.translation import ugettext_lazy as _
from django_mailbox import utils


logger = logging.getLogger(__name__)


class ModelApiError(Exception):
    pass


class Folder(models.Model):
    owner = models.IntegerField(_('Owner'), null=True, default=None)
    mailbox = models.ForeignKey(Mailbox, null=False, related_name="folders")
    name = models.CharField(max_length=128, null=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name}'


class Inbox(Mailbox):
    class Meta:
        proxy = True

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
        msg.save()
        message = self._get_dehydrated_message(message, msg)
        try:
            body = message.as_string()
        except KeyError as exc:
            # email.message.replace_header may raise 'KeyError' if the header
            # 'content-transfer-encoding' is missing
            logger.warning("Failed to parse message: %s", exc, )
            return None
        msg.set_body(body)
        if message['in-reply-to']:
            try:
                msg.in_reply_to = Mail.objects.filter(
                    message_id=message['in-reply-to'].strip()
                )[0]
            except IndexError:
                pass
        msg.save()
        return msg


class CustomMailbox(models.Model):
    owner = models.IntegerField(_('Owner'), null=True, default=None)
    inbox = models.OneToOneField(Inbox, related_name="mailer")
    smtp_host = models.CharField(max_length=128)
    smtp_port = models.IntegerField(default=587)


class Mail(Message):
    folder = models.ForeignKey(Folder, null=True, related_name='messages')
    bcc = models.TextField(null=True)
    draft = models.BooleanField(default=False)

    class Meta:
        ordering = ['-processed']

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
        try:
            payload = body.decode('ascii')
        except UnicodeDecodeError:
            payload = body.decode('utf-8')
        flat._payload = payload
        return self._rehydrate(flat)

    def send(self):
        msg = self.get_email_object()
        msg["Subject"] = self.subject
        msg["From"] = self.from_header
        msg["To"] = self.to_header
        msg["Bcc"] = self.bcc
        msg.set_charset('utf-8')

        server = smtplib.SMTP(self.mailbox.mailer.smtp_host, self.mailbox.mailer.smtp_port)
        server.ehlo()
        server.starttls()
        server.login(self.mailbox.username, self.mailbox.password)
        server.send_message(msg=msg)
        server.quit()

        self.outgoing = True
        self.save()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if self.outgoing:
            self.from_header = self.mailbox.from_email
        super(Mail, self).save()


class Contact(models.Model):
    folder = models.ForeignKey(Folder, null=True)
    email = models.EmailField(blank=False, null=True, default=None, unique=True)
    name = models.CharField(max_length=128, null=True)

    class Meta:
        ordering = ['name']

    def assign_to(self, folder=None):
        # Check if assignment already exists for any folder and raise
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
