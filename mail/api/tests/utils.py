import shutil
import os

import pathlib
import uuid

from string import Template

from django_mailbox.models import Mailbox
from trood_auth_client.authentication import TroodUser

from mail.api.models import CustomMailbox


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
        inbox = Mailbox.objects.create(uri='maildir://' + self.box_path)
        inbox.from_email = "test@mail.com"
        self.mailbox = CustomMailbox.objects.create(owner=trood_user.id, inbox=inbox)

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