from rest_framework.test import APITestCase, APIClient
from rest_framework.reverse import reverse
from django.test import testcases
from hamcrest import *

from mail.api.models import Mail
from mail.api.serializers import MailSerializer
from mail.api.tests.utils import Maildir


class MailSerializerTestCase(testcases.TestCase):
    def setUp(self):
        self.maildir = Maildir()

    def tearDown(self):
        self.maildir.delete()

    def test_to_representation(self):
        mail = Mail.objects.create(
            mailbox=self.maildir.mailbox,
            subject='Subject',
            body='Body',
            from_header='from@mail.com',
            to_header='to@mail.com'

        )

        serialized_data = MailSerializer(instance=mail).data

        assert_that(serialized_data, has_entries({
            "subject": 'Subject',
            "body": 'Body',
            "from_address": ["from@mail.com"],
            "to": ["to@mail.com"]
        }))


class MailSerializerApiTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.template = self.client.post(
            reverse("mail:templates-list"),
            data={
                "alias": "TEST_TEMPLATE",
                "name": "Test template name",
                "subject": "This is test subject",
                "body": "This is test body"
            },
            format="json"
        )
        self.template_alias = self.template.json()['alias']

    def test_serialization(self):

        response = self.client.post(
            reverse("mail:mails-from-template"),
            data={
                "to": "test@example.com",
                "template": self.template_alias,
                "data": {}
            },
            format='json'
        )

        assert response.status_code == 400
