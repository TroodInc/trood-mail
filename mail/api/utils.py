import urllib.parse
from email.utils import parsedate_to_datetime

from django.conf import settings


def build_absolute_url(host, path, trailing_slash=True):
    """
    Miising slash fault tolerant absolute url builder
    """
    joined_url = urllib.parse.urljoin(host.strip('/'), path.strip('/'))
    if trailing_slash:
        joined_url = joined_url + '/'
    return joined_url

def mail_fetching_filter(message):
    if 'date' in message:
        date = parsedate_to_datetime(message['date']).date()
        if date < settings.SKIP_MAILS_BEFORE:
            return False

    return True
  