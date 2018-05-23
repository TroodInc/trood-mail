# encoding: utf-8
from django.conf import settings
from django.conf.urls import url, include
from rest_framework import routers
from rest_framework.documentation import include_docs_urls

from mail.api.views import MailboxViewSet, MailViewSet, FolderViewSet, ContactViewSet

router = routers.DefaultRouter()

router.register(r'mailboxes', MailboxViewSet, base_name="mailboxes")
router.register(r'mails', MailViewSet, base_name="mails")
router.register(r'folders', FolderViewSet, base_name="folders")
router.register(r'contacts', ContactViewSet, base_name="contacts")

urlpatterns = [
    url(r'^api/v1.0/', include(router.urls, namespace='api')),
]
if settings.DEBUG:
    urlpatterns.append(url(r'^docs/', include_docs_urls(title='Trood Email')))
