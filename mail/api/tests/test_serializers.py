from django.test import testcases

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

        expected_data = {
             'id': mail.id,
             'mailbox': self.maildir.mailbox.id,
             'subject': 'Subject',
             'body': 'Body',
             'to': ['to@mail.com'],
             'bcc': None,
             'encoded': False,
             'from_address': ['from@mail.com'],
             'read': None,
             'outgoing': False,
             'in_reply_to': None,
             'replies': [],
             'folder': None,
             'attachments': []
        }

        assert serialized_data == expected_data
