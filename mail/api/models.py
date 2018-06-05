import logging
import smtplib

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


class CustomMailbox(models.Model):
    inbox = models.OneToOneField(Mailbox, related_name="mailer")
    smtp_host = models.CharField(max_length=128)
    smtp_port = models.IntegerField(default=587)


class Mail(Message):
    folder = models.ForeignKey(Folder, null=True, related_name='messages')
    bcc = models.TextField(null=True)
    draft = models.BooleanField(default=False)

    def send(self):
        msg = self.get_email_object()
        msg["Subject"] = self.subject
        msg["From"] = self.from_header
        msg["To"] = self.to_header
        msg["Bcc"] = self.bcc

        server = smtplib.SMTP(self.mailbox.mailer.smtp_host, self.mailbox.mailer.smtp_port)
        server.ehlo()
        server.starttls()
        server.login(self.mailbox.username, self.mailbox.password)
        server.send_message(msg=msg)
        server.quit()

        self.outgoing = True
        self.save()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        self.from_header = self.mailbox.from_email
        super(Mail, self).save()


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
