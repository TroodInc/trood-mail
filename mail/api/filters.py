from django_filters.rest_framework import filters, FilterSet

from mail.api.models import Mail


class ChainsFilter(FilterSet):
    folder = filters.CharFilter(method='filter_folder')

    class Meta:
        model = Mail
        fields = ('outgoing', 'chain')

    def filter_folder(self, qs, name, value):
        if value == 'inbox':
            return qs.exclude(**{'chain__folders__owner': self.request.user.id})

        elif value == 'outbox':
            filter_obj = {'outgoing': True}

        else:
            filter_obj = {'chain__folders__in': value}

        return qs.filter(**filter_obj)
