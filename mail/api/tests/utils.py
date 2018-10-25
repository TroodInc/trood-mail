import shutil
import os

import pathlib
import uuid

from string import Template

from trood_auth_client.authentication import TroodUser

from mail.api.models import Mailbox
import tempfile
import base64

from django.core.files import File

trood_user = TroodUser({
    "id": 1,
})


class Maildir:
    """
    Encapsulate local mail dir creation and wirin it with Mailbox entity
    """
    def __init__(self):
        # Create temporary dir structure to let maildir protocol work
        self.box_path = os.path.join(os.path.dirname(__file__), f'box{uuid.uuid4()}')
        self.new_path = os.path.join(self.box_path, 'new')
        self.cur_path = os.path.join(self.box_path, 'cur')

        pathlib.Path(self.box_path).mkdir(parents=True, exist_ok=True)
        pathlib.Path(self.new_path).mkdir(parents=True, exist_ok=True)
        pathlib.Path(self.cur_path).mkdir(parents=True, exist_ok=True)

        # To let maildir protocol works,
        # there are should be new,cur dirs in local mail dir path
        self.mailbox = Mailbox.objects.create(owner=trood_user.id, uri='maildir://' + self.box_path, from_email="test@mail.com")

    def delete(self):
        # Should be invoked explicitly,
        # otherwise maildir folder structure will stay in system
        shutil.rmtree(self.box_path)

    def create_mail(self, contact_name, contact_mail,
                    email_template='generic_message_template.eml'):
        template_path = os.path.join(os.path.dirname(__file__),
                                     'messages',
                                     email_template)
        template_file = open(template_path)
        src = Template(template_file.read())
        result = src.substitute({'contact_name': contact_name,
                                 'contact_mail': contact_mail})
        return result

    def send_mail(self, content):
        mail_filename = ''.join(['message', str(uuid.uuid4()), '.eml'])

        mail_path = os.path.join(self.new_path, mail_filename)
        with open(mail_path, 'w') as f:
            f.write(content)
        return mail_path


def create_temp_file(ext='.txt', data=None):
    _, filename = tempfile.mkstemp(ext)
    if data:
        tmp_file = open(filename, 'wb')
        tmp_file.write(base64.b64decode(data))
    else:
        tmp_file = open(filename, 'w')
        tmp_file.write('abcdef')

    tmp_file.close()
    tmp_file = open(filename, 'rb')
    return tmp_file, filename


def create_django_temp_file(ext):
    file, path = create_temp_file(ext)
    django_file = File(open(file.name, "rb"))
    return django_file