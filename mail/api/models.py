#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import os
import sys
import six
import gzip
import uuid
import email
import base64
import logging
import os.path
import mimetypes

from email.utils import parseaddr
from email.mime.text import MIMEText
from email.message import EmailMessage
from email import utils as email_utils

from jsonfield import JSONField
from tempfile import NamedTemporaryFile
from email.encoders import encode_quopri
from email.encoders import encode_base64
from quopri import encode as encode_quopri
from email.mime.multipart import MIMEMultipart
from email.utils import parsedate_to_datetime
from email.message import Message as EmailMessage

from django.template import Context
from django.template import Template as DjangoTemplate
from six.moves.urllib.parse import parse_qs, unquote, urlparse

import django

from django.core.files.base import ContentFile, File
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import now

import mail.api.utils as utils
from mail.api.signals import message_received
from mail.api.transports import Pop3Transport, ImapTransport, \
    MaildirTransport, MboxTransport, BabylTransport, MHTransport, \
    MMDFTransport, GmailImapTransport, OUTGOING

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


class ModelApiError(Exception):
    pass


class Chain(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)


# @todo: OPTIMIZZZZZEEEE !!!!!!!


class Mail(models.Model):
    bcc = models.TextField(null=True)
    draft = models.BooleanField(default=False)
    chain = models.ForeignKey(Chain, null=True, on_delete=models.SET_NULL)

    mailbox = models.ForeignKey(
        'Mailbox', verbose_name=_(u'Mailbox'), on_delete=models.SET_NULL, null=True
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
        if not hasattr(self, '_email_object'):
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
            self._email_object = self._rehydrate(flat)
        return self._email_object

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
        self.mailbox.out_transport.send(message=self)
        self.outgoing = True
        self.save()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if self.outgoing:
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

        elif self.chain is None:
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
        rehydrated[name] = re.sub("\r\n", "", str(value))
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


class Template(models.Model):
    owner = models.IntegerField(_('Owner'), null=True, default=None)
    alias = models.CharField(_(u'Alias'), max_length=128, null=False, unique=True)
    name = models.CharField(_(u'Name'), max_length=128, null=False)
    subject = models.CharField(_(u'Subject'), max_length=128, null=False)
    body = models.TextField(_(u'Body'), blank=True, default="")

    def render(self, data):
        body_template = DjangoTemplate(self.body)

        return {
            "subject": self.subject.format(**data),
            "body": body_template.render(Context(data)),
        }


class ActiveMailboxManager(models.Manager):
    def get_queryset(self):
        return super(ActiveMailboxManager, self).get_queryset().filter(
            active=True,
        )


class Mailbox(models.Model):
    out_type = models.CharField(
        _(u'Outgoing transport'),
        choices=((i.name, _(i.title)) for i in OUTGOING.values()),
        max_length=128,
        null=True
    )
    out_config = JSONField(null=True)

    name = models.CharField(_(u'Name'), max_length=255,)
    owner = models.IntegerField(_('Owner'), null=True, default=None)

    custom_query = models.CharField(max_length=512, null=True)

    shared = models.BooleanField(default=False)

    uri = models.CharField(
        _(u'URI'), max_length=255, blank=True, null=True, default=None,
        help_text=(_(
            "Example: imap+ssl://myusername:mypassword@someserver <br />"
            "<br />"
            "Internet transports include 'imap' and 'pop3'; "
            "common local file transports include 'maildir', 'mbox', "
            "and less commonly 'babyl', 'mh', and 'mmdf'. <br />"
            "<br />"
            "Be sure to urlencode your username and password should they "
            "contain illegal characters (like @, :, etc)."
        )),
    )

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

    active = models.BooleanField(
        _(u'Active'), blank=True, default=True,
        help_text=(_(
            "Check this e-mail inbox for new e-mail messages during polling "
            "cycles.  This checkbox does not have an effect upon whether "
            "mail is collected here when this mailbox receives mail from a "
            "pipe, and does not affect whether e-mail messages can be "
            "dispatched from this mailbox. "
        )),
    )

    last_polling = models.DateTimeField(
        _(u"Last polling"), blank=True, null=True,
        help_text=(_("The time of last successful polling for messages."
                     "It is blank for new mailboxes and is not set for "
                     "mailboxes that only receive messages via a pipe."
         )),
    )

    objects = models.Manager()
    active_mailboxes = ActiveMailboxManager()

    @property
    def _protocol_info(self):
        return urlparse(self.uri)

    @property
    def _query_string(self):
        return parse_qs(self._protocol_info.query)

    @property
    def _domain(self):
        return self._protocol_info.hostname

    @property
    def port(self):
        """Returns the port to use for fetching messages."""
        return self._protocol_info.port

    @property
    def username(self):
        """Returns the username to use for fetching messages."""
        return unquote(self._protocol_info.username)

    @property
    def password(self):
        """Returns the password to use for fetching messages."""
        return unquote(self._protocol_info.password)

    @property
    def location(self):
        """Returns the location (domain and path) of messages."""
        return self._domain if self._domain else '' + self._protocol_info.path

    @property
    def type(self):
        """Returns the 'transport' name for this mailbox."""
        scheme = self._protocol_info.scheme.lower()
        if '+' in scheme:
            return scheme.split('+')[0]
        return scheme

    @property
    def use_ssl(self):
        """Returns whether or not this mailbox's connection uses SSL."""
        return '+ssl' in self._protocol_info.scheme.lower()

    @property
    def use_tls(self):
        """Returns whether or not this mailbox's connection uses STARTTLS."""
        return '+tls' in self._protocol_info.scheme.lower()

    @property
    def archive(self):
        """Returns (if specified) the folder to archive messages to."""
        archive_folder = self._query_string.get('archive', None)
        if not archive_folder:
            return None
        return archive_folder[0]

    @property
    def folder(self):
        """Returns (if specified) the folder to fetch mail from."""
        folder = self._query_string.get('folder', None)
        if not folder:
            return None
        return folder[0]

    @property
    def out_transport(self):
        return OUTGOING[self.out_type](self.out_config)

    def get_connection(self):
        """Returns the transport instance for this mailbox.

        These will always be instances of
        `django_mailbox.transports.base.EmailTransport`.

        """
        if not self.uri:
            return None
        elif self.type == 'imap':
            conn = ImapTransport(
                self.location,
                port=self.port if self.port else None,
                ssl=self.use_ssl,
                tls=self.use_tls,
                archive=self.archive,
                folder=self.folder
            )
            conn.connect(self.username, self.password)
        elif self.type == 'gmail':
            conn = GmailImapTransport(
                self.location,
                port=self.port if self.port else None,
                ssl=True,
                archive=self.archive
            )
            conn.connect(self.username, self.password)
        elif self.type == 'pop3':
            conn = Pop3Transport(
                self.location,
                port=self.port if self.port else None,
                ssl=self.use_ssl
            )
            conn.connect(self.username, self.password)
        elif self.type == 'maildir':
            conn = MaildirTransport(self.location)
        elif self.type == 'mbox':
            conn = MboxTransport(self.location)
        elif self.type == 'babyl':
            conn = BabylTransport(self.location)
        elif self.type == 'mh':
            conn = MHTransport(self.location)
        elif self.type == 'mmdf':
            conn = MMDFTransport(self.location)
        return conn

    def process_incoming_message(self, message):
        """Process a message incoming to this mailbox."""
        msg = self._process_message(message)
        if msg is None:
            return None
        msg.outgoing = False
        msg.save()

        message_received.send(sender=self, message=msg)

        return msg

    def record_outgoing_message(self, message):
        """Record an outgoing message associated with this mailbox."""
        msg = self._process_message(message)
        if msg is None:
            return None
        msg.outgoing = True
        msg.save()
        return msg

    def _get_dehydrated_message(self, msg, record):
        settings = utils.get_settings()

        new = EmailMessage()
        if msg.is_multipart():
            for header, value in msg.items():
                # new[header] = value.replace('\n', '').replace('\r', '')
                new[header] = value
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
                filename or (uuid.uuid4().hex + extension),
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
        msg._email_object = message # remove ?
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
            logger.warning("Failed to parse message: %s", exc,)
            return None
        msg.set_body(body)

        if 'date' in message:
            msg.date = parsedate_to_datetime(message['date'])

        msg.save()
        return msg

    def _process_save_original_message(self, message, msg):
        settings = utils.get_settings()
        if settings['compress_original_message']:
            with NamedTemporaryFile(suffix=".eml.gz") as fp_tmp:
                with gzip.GzipFile(fileobj=fp_tmp, mode="w") as fp:
                    fp.write(message.as_string().encode('utf-8'))
                msg.eml.save(
                    "%s.eml.gz" % (uuid.uuid4(), ),
                    File(fp_tmp),
                    save=False
                )

        else:
            msg.eml.save(
                '%s.eml' % uuid.uuid4(),
                ContentFile(message.as_string()),
                save=False
            )

    def get_new_mail(self, condition=None):
        """Connect to this transport and fetch new messages."""
        connection = self.get_connection()
        if not connection:
            return
        for message in connection.get_message(condition):
            msg = self.process_incoming_message(message)
            if not msg is None:
                yield msg
        self.last_polling = now()
        if django.VERSION >= (1, 5):  # Django 1.5 introduces update_fields
            self.save(update_fields=['last_polling'])
        else:
            self.save()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Mailbox')
        verbose_name_plural = _('Mailboxes')


class IncomingMessageManager(models.Manager):
    def get_queryset(self):
        return super(IncomingMessageManager, self).get_queryset().filter(
            outgoing=False,
        )


class OutgoingMessageManager(models.Manager):
    def get_queryset(self):
        return super(OutgoingMessageManager, self).get_queryset().filter(
            outgoing=True,
        )


class UnreadMessageManager(models.Manager):
    def get_queryset(self):
        return super(UnreadMessageManager, self).get_queryset().filter(
            read=None
        )

