import json
import shutil
import os

import pathlib
import uuid

from string import Template

from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED
from rest_framework.test import APITestCase
from rest_framework.test import APIClient

from mail.api.models import Contact, Folder, CustomMailbox


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
        self.mailbox = CustomMailbox.objects.create(uri='maildir://' + self.box_path)

    def delete(self):
        # Should be invoked explicitly,
        # otherwise maildir folder structure will stay in system
        shutil.rmtree(self.box_path)

    def create_mail(self, contact_name, contact_mail):
        template_path = os.path.join(os.path.dirname(__file__),
                                     'messages',
                                     'generic_message_template.eml')
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


class MailTestMixin:
    def send_fetch_email(self, emails):
        # Send another mail
        for ce in emails:
            content = self.maildir.create_mail('eugene', ce)
            mail = self.maildir.send_mail(content)

        # Fetch mail
        response = self.client.post(
            f'/api/v1.0/mailboxes/{self.maildir.mailbox.id}/fetch/',
            format='json')
        return response


class MailboxViewSetTestCase(MailTestMixin, APITestCase):
    def setUp(self):
        self.maildir = Maildir()
        self.client = APIClient()

    def test_create_mailbox(self):
        request_data = {
            'name': 'cool',
            'email': 'test@gmail.com',
            'password': 'qazxqazx',
            'type': 'imap',
            'host': 'imap.gmail.com',
            'port': 993,
            'secure': 'ssl',
            'active': True
        }
        response = self.client.post('/api/v1.0/mailboxes/', request_data, format='json')
        assert response.status_code == HTTP_201_CREATED

    def test_fetch_single_mailbox(self):
        content = self.maildir.create_mail('eugene', 'dharmagetic@gmail.com')
        mail = self.maildir.send_mail(content)

        response = self.client.post(f'/api/v1.0/mailboxes/{self.maildir.mailbox.id}/fetch/', format='json')

        assert response.status_code == HTTP_200_OK
        assert response.data['mails received'] == 1
        # Added contacts of sender and recipient
        assert response.data['contacts added'] == 2

    def test_contact_already_created(self):
        contact = Contact.objects.create(email='dharmagetic@gmail.com')

        # Send another one mail from same address
        # to ensure that's contacts already added
        fetch_response = self.send_fetch_email([contact.email])

        assert fetch_response.status_code == HTTP_200_OK
        assert fetch_response.data['mails received'] == 1
        # Created only recipient contact
        assert fetch_response.data['contacts added'] == 1

    def tearDown(self):
        self.maildir.delete()


class MailsViewSetTestCase(MailTestMixin, APITestCase):
    def setUp(self):
        self.maildir = Maildir()
        self.client = APIClient()

    def test_mails_gathered(self):
        num_of_mails = 7
        for i in range(0, num_of_mails):
            content = self.maildir.create_mail('eugene',
                                               'dharmagetic@gmail.com')
            mail = self.maildir.send_mail(content)

        # Fetch mails
        response = self.client.post(
            f'/api/v1.0/mailboxes/{self.maildir.mailbox.id}/fetch/', format='json')
        assert response.status_code == HTTP_200_OK
        assert response.data['mails received'] == num_of_mails
        assert response.data['contacts added'] == 2

        # Then gather them
        response = self.client.get(f'/api/v1.0/mails/', format='json')
        assert response.status_code == HTTP_200_OK
        assert num_of_mails == len(response.data)

    def test_move_single_mail(self):
        folder = Folder.objects.create(mailbox=self.maildir.mailbox, name='Leads')
        contact = Contact.objects.create(email='dharmagetic@gmail.com')

        self.send_fetch_email([contact.email])

        # Gather mails
        response = self.client.get(f'/api/v1.0/mails/')
        mail_id = response.data[0]['id']
        assert response.data[0]['folder'] == None

        # Move single mail to folder
        response = self.client.patch(f'/api/v1.0/mails/{mail_id}/',
                                     data={'folder': folder.id}, format='json')

        assert response.status_code == HTTP_200_OK
        assert response.data['id'] == mail_id
        assert response.data['folder'] == folder.id


    def tearDown(self):
        self.maildir.delete()


class FolderViewSetTestCase(MailTestMixin, APITestCase):
    def setUp(self):
        self.maildir = Maildir()
        self.client = APIClient()

    def test_create_folder_ok(self):
        request_data = {
            'mailbox': self.maildir.mailbox.id,
            'name': 'Test folder'
        }
        response = self.client.post('/api/v1.0/folders/',
                                    data=request_data, format='json')

        assert response.status_code == 201
        assert response.data['name'] == 'Test folder'
        assert response.data['mailbox'] == self.maildir.mailbox.id

    def test_bulk_move_mails_to_folder_not_move_already_moved(self):
        folder = Folder.objects.create(mailbox=self.maildir.mailbox, name='Leads')
        contact = Contact.objects.create(email='dharmagetic@gmail.com')

        self.send_fetch_email([contact.email])

        # Gather mail
        response = self.client.get(f'/api/v1.0/mails/', format='json')
        gathered_mails_response_data = json.loads(response.content)

        # Move mails to folder
        message_ids = [m['id'] for m in gathered_mails_response_data]
        request_data = {
            'messages': message_ids
        }
        response = self.client.post(
            f'/api/v1.0/folders/{folder.id}/bulk-move/',
            data=request_data,
            format='json'
        )
        assert response.status_code == HTTP_200_OK

        assert response.data['messages'] == message_ids
        assert response.data['moved_messages'] == message_ids

        # Try to move mails to folder once again, should not be moved
        message_ids = [m['id'] for m in gathered_mails_response_data]
        request_data = {
            'messages': message_ids
        }
        response = self.client.post(
            f'/api/v1.0/folders/{folder.id}/bulk-move/',
            data=request_data,
            format='json'
        )
        assert response.status_code == HTTP_200_OK

        assert response.data['messages'] == message_ids
        assert response.data['moved_messages'] == []

    def test_bulk_move_mails_from_folder_to_folder(self):
        contact = Contact.objects.create(email='dharmagetic@gmail.com')

        self.send_fetch_email([contact.email])

        # Gather mail
        response = self.client.get(f'/api/v1.0/mails/', format='json')
        gathered_mails_response_data = json.loads(response.content)

        # Move mails to folder
        message_ids = [m['id'] for m in gathered_mails_response_data]
        request_data = {
            'messages': message_ids
        }

        folder_leads = Folder.objects.create(mailbox=self.maildir.mailbox,
                                       name='Leads')

        response = self.client.post(
            f'/api/v1.0/folders/{folder_leads.id}/bulk-move/',
            data=request_data,
            format='json'
        )
        assert response.status_code == HTTP_200_OK

        assert response.data['messages'] == message_ids
        assert response.data['moved_messages'] == message_ids

        # Move from one folder to another
        message_ids = [m['id'] for m in gathered_mails_response_data]
        request_data = {
            'messages': message_ids
        }
        folder_sales = Folder.objects.create(mailbox=self.maildir.mailbox,
                                       name='Sales')
        response = self.client.post(
            f'/api/v1.0/folders/{folder_sales.id}/bulk-move/',
            data=request_data,
            format='json'
        )
        assert response.status_code == HTTP_200_OK

        assert list(folder_leads.messages.all()) == []
        assert response.data['messages'] == message_ids
        assert response.data['moved_messages'] == message_ids

    def tearDown(self):
        self.maildir.delete()


class AssignContactToFolderViewSetTestCase(MailTestMixin, APITestCase):
    def setUp(self):
        self.maildir = Maildir()
        self.client = APIClient()

    def test_assign_contact_to_folder(self):
        folder_sales = Folder.objects.create(mailbox=self.maildir.mailbox,
                                             name='Sales')
        contact = Contact.objects.create(email='dharmagetic@gmail.com',
                                         folder=folder_sales)

        self.send_fetch_email([contact.email])

        # Check that there is a message in assigned folder
        assert folder_sales.messages.count() == 1

    def test_unassign_contact_from_folder(self):
        folder_sales = Folder.objects.create(mailbox=self.maildir.mailbox,
                                             name='Sales')
        contact = Contact.objects.create(email='dharmagetic@gmail.com',
                                         folder=folder_sales)

        self.send_fetch_email([contact.email])

        response = self.client.patch(f'/api/v1.0/contacts/{contact.id}/',
                                     data={'folder': None}, format='json')
        assert response.status_code == HTTP_200_OK
        assert response.data['id'] == contact.id
        assert response.data['folder'] == None

        self.send_fetch_email([contact.email])

        assert folder_sales.messages.count() == 1


    def test_bulk_unassign_contacts_from_folder(self):
        folder_sales = Folder.objects.create(mailbox=self.maildir.mailbox,
                                             name='Sales')
        contact_emails = ['contact_1@sales.ru', 'contact_2@sales.ru',
                          'contact_3@sales.ru']
        contact1 = Contact.objects.create(folder=folder_sales,
                                          email=contact_emails[0])
        contact2 = Contact.objects.create(folder=folder_sales,
                                          email=contact_emails[1])
        contact3 = Contact.objects.create(folder=folder_sales,
                                          email=contact_emails[2])
        contacts = [contact1.id, contact2.id, contact3.id]

        self.send_fetch_email(contact_emails)

        # Unassign contacts from folder
        response = self.client.patch(f'/api/v1.0/folders/{folder_sales.id}/bulk-unassign/',
                                     data={'contacts': contacts}, format='json')
        assert response.status_code == HTTP_200_OK

        self.send_fetch_email(contact_emails)

        # Check that there is a still message count
        assert folder_sales.messages.count() == 3

    def tearDown(self):
        self.maildir.delete()