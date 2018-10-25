from mailbox import MMDF
from mail.api.transports.generic import GenericFileMailbox


class MMDFTransport(GenericFileMailbox):
    _variant = MMDF
