# encoding: utf-8
from django.conf import settings
from django.conf.urls import url, include
from django.conf.urls.static import static
from django.views.generic import TemplateView
from rest_framework import routers
from trood.contrib.django.apps.fixtures.views import TroodFixturesViewSet

from mail.api.views import MailboxViewSet, MailViewSet, FolderViewSet, ContactViewSet, ChainViewSet, TemplateViewSet
from trood.contrib.django.apps.meta.views import TroodMetaView

router = routers.DefaultRouter()

router.register(r'mailboxes', MailboxViewSet, base_name="mailboxes")
router.register(r'mails', MailViewSet, base_name="mails")
router.register(r'folders', FolderViewSet, base_name="folders")
router.register(r'contacts', ContactViewSet, base_name="contacts")
router.register(r'chains', ChainViewSet,  base_name="chains")
router.register(r'templates', TemplateViewSet,  base_name="templates")

if settings.DEBUG:
    router.register(r'fixtures', TroodFixturesViewSet, base_name='fixtures')

urlpatterns = [
    url(r'meta', TroodMetaView.as_view(), name='meta'),
    url(r'^api/v1.0/', include((router.urls, "mail"), namespace='api')),
]

if settings.DEBUG:
    urlpatterns += [
        url('swagger/', TemplateView.as_view(template_name='swagger_ui.html'), name='swagger-ui'),
    ] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
