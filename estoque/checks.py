from django.conf import settings
from django.core.checks import Error, register


@register()
def comunicacoes_externas_configuradas(app_configs, **kwargs):
    erros = []
    if settings.NOTIFICACOES_EMAIL_ENABLED and settings.EMAIL_BACKEND.endswith(
        '.smtp.EmailBackend'
    ):
        obrigatorias = {
            'EMAIL_HOST': settings.EMAIL_HOST,
            'EMAIL_HOST_USER': settings.EMAIL_HOST_USER,
            'EMAIL_HOST_PASSWORD': settings.EMAIL_HOST_PASSWORD,
            'DEFAULT_FROM_EMAIL': settings.DEFAULT_FROM_EMAIL,
        }
        ausentes = [nome for nome, valor in obrigatorias.items() if not valor]
        if ausentes:
            erros.append(Error(
                'O canal de e-mail está habilitado com configuração SMTP incompleta.',
                hint=f'Configure: {", ".join(ausentes)}.',
                id='estoque.E001',
            ))

    if settings.WHATSAPP_ENABLED:
        if settings.WHATSAPP_PROVIDER != 'meta':
            erros.append(Error(
                'WHATSAPP_ENABLED exige WHATSAPP_PROVIDER=meta.',
                id='estoque.E002',
            ))
        obrigatorias = {
            'WHATSAPP_API_BASE_URL': settings.WHATSAPP_API_BASE_URL,
            'WHATSAPP_ACCESS_TOKEN': settings.WHATSAPP_ACCESS_TOKEN,
            'WHATSAPP_PHONE_NUMBER_ID': settings.WHATSAPP_PHONE_NUMBER_ID,
            'WHATSAPP_WEBHOOK_VERIFY_TOKEN': settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN,
            'WHATSAPP_WEBHOOK_APP_SECRET': settings.WHATSAPP_WEBHOOK_APP_SECRET,
        }
        ausentes = [nome for nome, valor in obrigatorias.items() if not valor]
        if ausentes:
            erros.append(Error(
                'O canal WhatsApp está habilitado com configuração incompleta.',
                hint=f'Configure: {", ".join(ausentes)}.',
                id='estoque.E003',
            ))
    return erros
