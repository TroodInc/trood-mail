import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from rest_framework import status

from mail.api.utils import build_absolute_url
from trood.core.utils import get_service_token

class TroodFile(ContentFile):
    def __init__(self, content, options):
        self.meta = options
        self.file = content

    @property
    def type(self):
        return self.meta['mimetype']

    @property
    def size(self):
        return self.meta['size']

    @property
    def name(self):
        return self.meta['filename']


class TroodFileStorage(Storage):
    def __init__(self):
        self.host = settings.DEFAULT_FILE_STORAGE_HOST

    def _open(self, name, mode):
        detail_file_url = build_absolute_url(self.host,  f'api/v1.0/files/{name}/')
        response = requests.get(detail_file_url, headers={
            'Authorization': get_service_token()
        })

        if response.status_code == status.HTTP_200_OK:
            file_data = response.json()

            response = requests.get('http:' + file_data['file_url'], stream=True)
            if response.status_code == status.HTTP_200_OK:
                return TroodFile(response.raw, file_data)
            raise FileNotFoundError("File http:{} does not exists".format(file_data['file_url']))

        raise FileNotFoundError("File with id:{} does not exists".format(detail_file_url))

    def _save(self, name, content):
        try:
            file = self.open(name)
            return file.meta['id']

        except FileNotFoundError:

            url = build_absolute_url(self.host, 'api/v1.0/files/')

            headers = {
                'Authorization': get_service_token()
            }

            response = requests.post(url, files={'file': (name, content)}, data={'name': name}, headers=headers)

            response.raise_for_status()

            if response.status_code == status.HTTP_201_CREATED:
                return response.json()['id']


    def get_available_name(self, name, max_length=None):
        name = name.split('/')[-1]
        return name

    def url(self, name):
        return f'api/v1.0/files/{name}/'