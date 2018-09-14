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
            mailbox=self.maildir.mailbox.inbox,
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