from django_filters.rest_framework import filters, FilterSet

from mail.api.models import Mail


class MailsFilter(FilterSet):
    folder = filters.CharFilter(method='filter_folder')

    class Meta:
        model = Mail
        fields = ('outgoing', )

    def filter_folder(self, qs, name, value):
        if value == 'inbox':
            filter_obj = {'folder__isnull': True, 'outgoing': False}

        elif value == 'outbox':
            filter_obj = {'folder__isnull': True, 'outgoing': True}

        else:
            filter_obj = {'folder': value}

        return qs.filter(**filter_obj)
