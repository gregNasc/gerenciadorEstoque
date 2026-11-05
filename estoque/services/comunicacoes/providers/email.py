from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from .base import ProviderResult


class DisabledEmailProvider:
    def enviar_payload(self, **kwargs):
        return ProviderResult(
            sucesso=False,
            erro='Provedor de e-mail desabilitado.',
            repetivel=False,
        )


class DjangoEmailProvider:
    """Adaptador SMTP do Django isolado do domínio de Comunicados."""

    def enviar_payload(
        self,
        *,
        destino,
        payload,
        idempotency_key,
        execution_scope,
    ):
        mensagem = EmailMultiAlternatives(
            subject=payload['assunto'],
            body=payload['corpo'],
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destino],
            headers={'X-Idempotency-Key': idempotency_key},
        )
        enviados = mensagem.send(fail_silently=False)
        if enviados != 1:
            return ProviderResult(
                sucesso=False,
                erro='O backend de e-mail não confirmou o envio.',
                repetivel=True,
            )
        return ProviderResult(
            sucesso=True,
            provider_message_id=idempotency_key,
            resposta={
                'backend': settings.EMAIL_BACKEND,
                'aceita_pelo_backend': True,
            },
        )


def obter_provedor_email():
    if not settings.NOTIFICACOES_EMAIL_ENABLED:
        return DisabledEmailProvider()
    return DjangoEmailProvider()
