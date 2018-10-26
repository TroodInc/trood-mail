from mailbox import Babyl
from mail.api.transports.generic import GenericFileMailbox


class BabylTransport(GenericFileMailbox):
    _variant = Babyl
