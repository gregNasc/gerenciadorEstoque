from django.conf import settings

from .disabled import DisabledWhatsAppProvider
from .meta_whatsapp import MetaWhatsAppProvider


def obter_provedor():
    if settings.WHATSAPP_PROVIDER == 'meta':
        return MetaWhatsAppProvider()
    return DisabledWhatsAppProvider()


__all__ = ['obter_provedor', 'DisabledWhatsAppProvider', 'MetaWhatsAppProvider']

