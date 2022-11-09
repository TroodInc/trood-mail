import email

import six

# Do *not* remove this, we need to use this in subclasses of EmailTransport
if six.PY3:
    from email.errors import MessageParseError  # noqa: F401
else:
    from email.Errors import MessageParseError  # noqa: F401


class EmailTransport(object):
    def __init__(self, config=None):
        if config and self.config_class:
            serializer = self.config_class(data=config)
            if serializer.is_valid():
                self.config = serializer.validated_data

    def get_email_from_bytes(self, contents):
        if six.PY3:
            message = email.message_from_bytes(contents)
        else:
            message = email.message_from_string(contents)

        return message
