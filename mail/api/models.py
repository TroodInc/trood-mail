from django.db import models
from django_mailbox.models import Mailbox, Message


class Folder(models.Model):
    mailbox = models.ForeignKey(Mailbox, null=False, related_name="folders")
    name = models.CharField(max_length=128, null=False)
    messages = models.ManyToManyField(Message, related_name="folder", null=True)


class Contact(models.Model):
    email = models.EmailField(blank=False, null=True, default=None, unique=True)
    name = models.CharField(max_length=128, null=True)
