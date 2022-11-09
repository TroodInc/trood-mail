from unittest import mock

import pytest
from datetime import datetime

from django.conf import settings
from hamcrest import *
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND
from rest_framework.test import APITestCase
from rest_framework.test import APIClient

from mail.api.models import Contact, Folder, Mail, Template

from mail.api.tests.utils import Maildir, trood_user


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
        self.client.force_authenticate(user=trood_user)

        settings.SKIP_MAILS_BEFORE = datetime.strptime("01-01-2012", "%d-%m-%Y").date()

    def test_create_mailbox(self):
        request_data = {
            "name": "cool",
            "from_email": "email@example.com",
            "password": "demo",
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "out_type": "smtp",
            "out_config": {
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 465,
                "smtp_secure": "ssl"
            },
            "imap_secure": "ssl",
            "active": True
        }

        mocked_date = {
            "name": "cool",
            "from_email": "demo@gmail.com",
            "uri": "imap+ssl://myusername:mypassword@someserver",
            "active": True
        }
        with mock.patch('mail.api.serializers.TroodMailboxSerializer.validate', mock.Mock(return_value=mocked_date)):
            response = self.client.post('/api/v1.0/mailboxes/', request_data, format='json')
            print(response.json())
            assert_that(response.status_code, is_(HTTP_201_CREATED))

    @pytest.mark.skip(msg="smtp validation need to be fixed")
    def test_failed_creating_mailbox(self):
        request_data = {
            "name": "cool",
            "from_email": "email@example.com",
            "password": "demo",
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "out_type": "smtp",
            "out_config": {
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 465,
                "smtp_secure": "ssl"
            },
            "imap_secure": "ssl",
            "active": True
        }

        response = self.client.post('/api/v1.0/mailboxes/', request_data, format='json')
        assert_that(response.status_code, is_(HTTP_400_BAD_REQUEST))
        assert_that(response.json()['non_field_errors'], is_(["SMTP server login error: invalid email or password"]))

    def test_fetch_single_mailbox(self):
        content = self.maildir.create_mail('eugene', 'dharmagetic@gmail.com')
        mail = self.maildir.send_mail(content)

        response = self.client.post(
            f'/api/v1.0/mailboxes/{self.maildir.mailbox.id}/fetch/',
            format='json'
        )

        assert response.status_code == HTTP_200_OK
        assert response.data['mails_received'] == 1
        # Added contacts of sender and recipient
        assert response.data['contacts_added'] == 2


    def test_contact_already_created(self):
        contact = Contact.objects.create(email='dharmagetic@gmail.com')

        # Send another one mail from same address
        # to ensure that's contacts already added
        fetch_response = self.send_fetch_email([contact.email])

        assert fetch_response.status_code == HTTP_200_OK
        assert fetch_response.data['mails_received'] == 1
        # Created only recipient contact
        assert fetch_response.data['contacts_added'] == 1

    def tearDown(self):
        self.maildir.delete()


class MailsViewSetTestCase(MailTestMixin, APITestCase):
    def setUp(self):
        self.maildir = Maildir()
        self.client = APIClient()
        self.client.force_authenticate(user=trood_user)

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
        assert response.data['mails_received'] == num_of_mails
        assert response.data['contacts_added'] == 2

        # Then gather them
        response = self.client.get(f'/api/v1.0/mails/', format='json')
        assert response.status_code == HTTP_200_OK
        assert num_of_mails == response.data['count']

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

    def test_can_search(self):
        mail_1 = Mail.objects.create(
            mailbox=self.maildir.mailbox,
            subject="sales mail",
        )

        mail_2 = Mail.objects.create(
            mailbox=self.maildir.mailbox,
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


class TemplateTest(APITestCase):

    def test_template_renders(self):
        template = Template.objects.create(
            alias="TEST_TEMPLATE",
            subject="Hello {username}!",
            body="It as {{ test_name }} test!"
        )

        data = template.render({"username": "test_user", "test_name": "template"})

        assert_that(data, equal_to({
            "subject": "Hello test_user!",
            "body": "It as template test!"
        }))


class FolderViewSetTestCase(MailTestMixin, APITestCase):
    def setUp(self):
        self.maildir = Maildir()
        self.client = APIClient()
        self.client.force_authenticate(user=trood_user)

    def test_create_folder_ok(self):
        request_data = {'name': 'Test folder'}
        response = self.client.post('/api/v1.0/folders/', data=request_data, format='json')

        assert response.status_code == 201
        assert response.data['name'] == 'Test folder'

    def tearDown(self):
        self.maildir.delete()


class AssignContactToFolderViewSetTestCase(MailTestMixin, APITestCase):
    def setUp(self):
        self.maildir = Maildir()
        self.client = APIClient()
        self.client.force_authenticate(user=trood_user)

    # todo fix test
    def test_assign_contact_to_folder(self):
        folder_sales = Folder.objects.create(name='Sales')
        contact = Contact.objects.create(email='dharmagetic@gmail.com', folder=folder_sales)

        self.send_fetch_email([contact.email])

    # todo fix test
    def test_unassign_contact_from_folder(self):
        folder_sales = Folder.objects.create(name='Sales')
        contact = Contact.objects.create(email='dharmagetic@gmail.com', folder=folder_sales)

        self.send_fetch_email([contact.email])

        response = self.client.patch(f'/api/v1.0/contacts/{contact.id}/', data={'folder': None}, format='json')
        assert response.status_code == HTTP_200_OK
        assert response.data['id'] == contact.id

        self.send_fetch_email([contact.email])

    # todo fix test
    def test_bulk_unassign_contacts_from_folder(self):
        folder_sales = Folder.objects.create(name='Sales')
        contact_emails = ['contact_1@sales.ru', 'contact_2@sales.ru', 'contact_3@sales.ru']
        contact1 = Contact.objects.create(folder=folder_sales, email=contact_emails[0])
        contact2 = Contact.objects.create(folder=folder_sales, email=contact_emails[1])
        contact3 = Contact.objects.create(folder=folder_sales, email=contact_emails[2])
        contacts = [contact1.id, contact2.id, contact3.id]

        self.send_fetch_email(contact_emails)

        # Unassign contacts from folder
        response = self.client.patch(
            f'/api/v1.0/folders/{folder_sales.id}/bulk-unassign/', data={'contacts': contacts}, format='json'
        )
        assert response.status_code == HTTP_200_OK

        self.send_fetch_email(contact_emails)

    def tearDown(self):
        self.maildir.delete()