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
            return qs.filter(received__gte=1)

        elif value == 'outbox':
            filter_obj = {'sent__gt': 0}

        else:
            filter_obj = {'folders': value}

        return qs.filter(**filter_obj)
