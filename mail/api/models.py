import logging

from django.db import models
from django_mailbox.models import Mailbox, Message
from django_mailbox import utils


logger = logging.getLogger(__name__)


class ModelApiError(Exception):
    pass


class Folder(models.Model):
    mailbox = models.ForeignKey(Mailbox, null=False, related_name="folders")
    name = models.CharField(max_length=128, null=False)

    def __str__(self):
        return f'{self.name}'


class CustomMailbox(Mailbox):
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
            logger.warning("Failed to parse message: %s", exc,)
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


class Mail(Message):
    folder = models.ForeignKey(Folder, null=True, related_name='messages')


class Contact(models.Model):
    folder = models.ForeignKey(Folder, null=True)
    email = models.EmailField(blank=False, null=True, default=None, unique=True)
    name = models.CharField(max_length=128, null=True)

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


class AssignContactToFolder(models.Model):
    contact = models.ForeignKey(Contact, null=False, related_name='contacts')
    folder = models.ForeignKey(Folder, null=False, related_name='folders')

    class Meta:
        unique_together = (('contact', 'folder'),)

    def __str__(self):
        return f'{self.contact.email}:{self.folder.name}'
