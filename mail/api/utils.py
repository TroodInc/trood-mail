import urllib.parse


def build_absolute_url(host, path, trailing_slash=True):
    """
    Miising slash fault tolerant absolute url builder
    """
    joined_url = urllib.parse.urljoin(host.strip('/'), path.strip('/'))
    if trailing_slash:
        joined_url = joined_url + '/'
    return joined_url
