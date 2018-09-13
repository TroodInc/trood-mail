from django.db.models import Count, Q
from django_filters.rest_framework import filters, FilterSet

from mail.api.models import Chain


class ChainsFilter(FilterSet):
    folder = filters.CharFilter(method='filter_folder')

    class Meta:
        model = Chain
        fields = ('folders', 'id')

    def filter_folder(self, qs, name, value):
        if value == 'inbox':
            qs = qs.exclude(folders__owner=self.request.user.id)

            return qs.annotate(
                received=Count("mail__pk", filter=Q(mail__outgoing=False))
            ).filter(received__gte=1)

        elif value == 'outbox':

            return qs.annotate(
                sent=Count("mail__pk", filter=Q(mail__outgoing=True))
            ).filter(sent__gte=1)

        else:
            return qs.filter(folders=value)
