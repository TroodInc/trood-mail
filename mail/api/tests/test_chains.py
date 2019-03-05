from hamcrest import *
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient

from mail.api.models import Mail
from mail.api.tests.utils import trood_user, Maildir


class ChainsTestCase(APITestCase):

    def setUp(self):
        self.maildir = Maildir()
        self.client = APIClient()
        self.client.force_authenticate(user=trood_user)

        first = Mail.objects.create(mailbox=self.maildir.mailbox, subject="First mail in chain")

        self.chain = first.chain

        Mail.objects.create(mailbox=self.maildir.mailbox, subject="Second mail in chain", in_reply_to=first)

        Mail.objects.create(mailbox=self.maildir.mailbox, subject="Read mail in chain", in_reply_to=first, is_read=True)
        Mail.objects.create(mailbox=self.maildir.mailbox, subject="Read mail in chain", in_reply_to=first, is_read=True)

        Mail.objects.create(mailbox=self.maildir.mailbox, subject="Other mail in chain", chain=self.chain)
        Mail.objects.create(mailbox=self.maildir.mailbox, subject="Other mail in chain", chain=self.chain)
        Mail.objects.create(mailbox=self.maildir.mailbox, subject="Other mail in chain", chain=self.chain)

        for a in range(2):
            out = Mail.objects.create(mailbox=self.maildir.mailbox, subject="Outgoing mail {} in chain".format(a), chain=self.chain)
            out.outgoing = True
            out.save()

    def test_chains_list_count(self):
        url = reverse('api:chains-list')

        response = self.client.get(url)

        assert_that(response.status_code, equal_to(status.HTTP_200_OK))

        chain = response.data["results"][0]

        assert_that(chain['total'], equal_to(9))
        assert_that(chain['unread'], equal_to(5))
        assert_that(chain['sent'], equal_to(2))

    def test_chains_detail_count(self):
        url = reverse('api:chains-detail', kwargs={'pk': self.chain.id})

        response = self.client.get(url)

        assert_that(response.status_code, equal_to(status.HTTP_200_OK))

        assert_that(response.data['total'], equal_to(9))
        assert_that(response.data['unread'], equal_to(5))
        assert_that(response.data['sent'], equal_to(2))
