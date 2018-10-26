from mailbox import MH
from mail.api.transports.generic import GenericFileMailbox


class MHTransport(GenericFileMailbox):
    _variant = MH
