from .base import ProviderResult


class DisabledWhatsAppProvider:
    def enviar_payload(self, **kwargs):
        return ProviderResult(sucesso=False, erro='Provedor WhatsApp desabilitado.', repetivel=False)

