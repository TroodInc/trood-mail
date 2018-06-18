import json
import shutil
import os

import pathlib
import uuid

from string import Template

from django_mailbox.models import Mailbox
from hamcrest import *
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, \
    HTTP_404_NOT_FOUND
from rest_framework.test import APITestCase
from rest_framework.test import APIClient

from mail.api.models import Contact, Folder, CustomMailbox, Mail


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
        self.mailbox = CustomMailbox.objects.create(inbox=inbox)

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

    def generate_mails(self, from_contact_name='eugene',
                       from_contact_email='dharmagetic@gmail.com', count=10):
        num_of_mails = count
        for i in range(0, count):
            content = self.maildir.create_mail(from_contact_name,
                                               from_contact_email)
            mail = self.maildir.send_mail(content)
        # Fetch mail
        response = self.client.post(
            f'/api/v1.0/mailboxes/{self.maildir.mailbox.id}/fetch/',
            format='json')
        return count


class MailboxViewSetTestCase(MailTestMixin, APITestCase):
    def setUp(self):
        self.maildir = Maildir()
        self.client = APIClient()

    def test_create_mailbox(self):
        request_data = {
            "name": "cool",
            "email": "testmirrorcx@gmail.com",
            "password": "qazxqazx",
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "secure": "ssl",
            "active": True
        }
        response = self.client.post('/api/v1.0/mailboxes/', request_data, format='json')
        assert response.status_code == HTTP_201_CREATED

    def test_fetch_single_mailbox(self):
        content = self.maildir.create_mail('eugene', 'dharmagetic@gmail.com')
        mail = self.maildir.send_mail(content)

        response = self.client.post(
            f'/api/v1.0/mailboxes/{self.maildir.mailbox.id}/fetch/',
            format='json'
        )

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
        assert num_of_mails == response.data['count']

    def test_move_single_mail(self):
        folder = Folder.objects.create(mailbox=self.maildir.mailbox.inbox, name='Leads')
        contact = Contact.objects.create(email='dharmagetic@gmail.com')

        self.send_fetch_email([contact.email])

        # Gather mails
        response = self.client.get(f'/api/v1.0/mails/')
        mail_id = response.data['results'][0]['id']
        assert response.data['results'][0]['folder'] == None

        # Move single mail to folder
        response = self.client.patch(f'/api/v1.0/mails/{mail_id}/',
                                     data={'folder': folder.id}, format='json')

        assert response.status_code == HTTP_200_OK
        assert response.data['id'] == mail_id
        assert response.data['folder'] == folder.id

    def test_pagination_ok(self):
        generated_mails_count = self.generate_mails(count=25)
        response = self.client.get(f'/api/v1.0/mails/?page_size=5&page=4',
                                   format='json')
        assert response.status_code == HTTP_200_OK
        assert response.data['count'] == generated_mails_count
        assert response.data['previous'] == \
               'http://testserver/api/v1.0/mails/?page=3&page_size=5'
        assert response.data['next'] == \
               'http://testserver/api/v1.0/mails/?page=5&page_size=5'

    def test_pagination_fail(self):
        generated_mails_count = self.generate_mails(count=25)
        response = self.client.get(f'/api/v1.0/mails/?page_size=50&page=2',
                                   format='json')
        assert response.status_code == HTTP_404_NOT_FOUND
        assert response.data['detail'] == 'Invalid page.'

    def test_can_filter_by_folder(self):

        folder_sales = Folder.objects.create(mailbox=self.maildir.mailbox.inbox, name='Sales')

        mail_in_folder = Mail.objects.create(
            mailbox=self.maildir.mailbox.inbox,
            subject="sales mail", folder=folder_sales
        )

        inbox_mail = Mail.objects.create(
            mailbox=self.maildir.mailbox.inbox,
            subject="test mail"
        )

        outgoing_mail = Mail.objects.create(
            mailbox=self.maildir.mailbox.inbox,
            subject="outgoing", outgoing=True
        )

        response = self.client.get(f'/api/v1.0/mails/?folder={folder_sales.id}', )

        assert_that(response.status_code, equal_to(HTTP_200_OK))
        assert_that(response.data['results'], has_length(1))
        assert_that(response.data['results'][0]['id'], equal_to(mail_in_folder.id))

        response = self.client.get(f'/api/v1.0/mails/?folder=inbox', )

        assert_that(response.status_code, equal_to(HTTP_200_OK))
        assert_that(response.data['results'], has_length(1))
        assert_that(response.data['results'][0]['id'], equal_to(inbox_mail.id))

        response = self.client.get(f'/api/v1.0/mails/?folder=outbox', )

        assert_that(response.status_code, equal_to(HTTP_200_OK))
        assert_that(response.data['results'], has_length(1))
        assert_that(response.data['results'][0]['id'], equal_to(outgoing_mail.id))

    def test_can_search(self):
        mail_1 = Mail.objects.create(
            mailbox=self.maildir.mailbox.inbox,
            subject="sales mail",
        )

        mail_2 = Mail.objects.create(
            mailbox=self.maildir.mailbox.inbox,
            subject="test mail",
            from_header="boss@mail.com"
        )

        response = self.client.get('/api/v1.0/mails/?search=sales', )

        assert_that(response.status_code, equal_to(HTTP_200_OK))
        assert_that(response.data['results'], has_length(1))
        assert_that(response.data['results'][0]['id'], equal_to(mail_1.id))

        response = self.client.get('/api/v1.0/mails/?search=boss', )

        assert_that(response.status_code, equal_to(HTTP_200_OK))
        assert_that(response.data['results'], has_length(1))
        assert_that(response.data['results'][0]['id'], equal_to(mail_2.id))

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
        folder = Folder.objects.create(mailbox=self.maildir.mailbox.inbox, name='Leads')
        contact = Contact.objects.create(email='dharmagetic@gmail.com')

        self.send_fetch_email([contact.email])

        # Gather mail
        response = self.client.get(f'/api/v1.0/mails/', format='json')
        gathered_mails_response_data = json.loads(response.content)

        # Move mails to folder
        message_ids = [m['id'] for m in gathered_mails_response_data['results']]
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
        message_ids = [m['id'] for m in gathered_mails_response_data['results']]
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
        message_ids = [m['id'] for m in gathered_mails_response_data['results']]
        request_data = {
            'messages': message_ids
        }

        folder_leads = Folder.objects.create(mailbox=self.maildir.mailbox.inbox,
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
        message_ids = [m['id'] for m in gathered_mails_response_data['results']]
        request_data = {
            'messages': message_ids
        }
        folder_sales = Folder.objects.create(mailbox=self.maildir.mailbox.inbox,
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
        folder_sales = Folder.objects.create(mailbox=self.maildir.mailbox.inbox,
                                             name='Sales')
        contact = Contact.objects.create(email='dharmagetic@gmail.com',
                                         folder=folder_sales)

        self.send_fetch_email([contact.email])

        # Check that there is a message in assigned folder
        assert folder_sales.messages.count() == 1

    def test_unassign_contact_from_folder(self):
        folder_sales = Folder.objects.create(mailbox=self.maildir.mailbox.inbox,
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
        folder_sales = Folder.objects.create(mailbox=self.maildir.mailbox.inbox,
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