import requests
from rest_framework import fields
from rest_framework.serializers import Serializer

from mail.api.transports.base import EmailTransport


class UnisenderConfigSerializer(Serializer):
    api_key = fields.CharField(max_length=128)
    sender_name = fields.CharField(max_length=128)


class UnisenderTransport(EmailTransport):
    name = "unisender"
    title = "Unisender"

    config_class = UnisenderConfigSerializer

    def send(self, message):
        response = requests.get(
            "https://api.unisender.com/ru/api/sendEmail",
            params={
                "format": "json",
                "api_key": self.config['api_key'],
                "email": message.to_addresses,
                "sender_name": self.config['sender_name'],
                "sender_email": message.from_address,
                "subject": message.subject,
                "body": message.html,
                "list_id": 1
            }
        )

        print(response.status_code)
