from django import template
from django.conf import settings

register = template.Library()


@register.filter(name='get')
def get(d, k):
    return d.get(k, None)


@register.simple_tag(name='global')
def get_global(name):
    # @todo: replace with configurable app from TroodLib
    return settings.GLOBAL_CONFIGURABLE.get(name, None)
