import requests
from django.conf import settings

from .base import ProviderResult


class MetaWhatsAppProvider:
    def enviar_template(self, *, destino, template_codigo, idioma, parametros, idempotency_key):
        if not settings.WHATSAPP_API_BASE_URL or not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
            return ProviderResult(sucesso=False, erro='Configuração do provedor incompleta.', repetivel=False)
        url = f'{settings.WHATSAPP_API_BASE_URL.rstrip("/")}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages'
        corpo_parametros = [
            {'type': 'text', 'text': str(valor)}
            for valor in parametros.values()
            if valor not in (None, '')
        ]
        payload = {
            'messaging_product': 'whatsapp',
            'to': destino,
            'type': 'template',
            'template': {
                'name': template_codigo,
                'language': {'code': idioma or 'pt_BR'},
                'components': [{'type': 'body', 'parameters': corpo_parametros}],
            },
        }
        try:
            resposta = requests.post(
                url,
                json=payload,
                headers={
                    'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
                    'Content-Type': 'application/json',
                    'X-Idempotency-Key': idempotency_key,
                },
                timeout=settings.WHATSAPP_TIMEOUT,
            )
            dados = resposta.json() if resposta.content else {}
        except requests.RequestException as exc:
            return ProviderResult(sucesso=False, erro=str(exc), repetivel=True)
        except ValueError:
            dados = {}
        if 200 <= resposta.status_code < 300:
            mensagens = dados.get('messages') or []
            return ProviderResult(
                sucesso=True,
                provider_message_id=mensagens[0].get('id', '') if mensagens else '',
                resposta=dados,
            )
        return ProviderResult(
            sucesso=False,
            resposta=dados,
            erro=f'Provedor retornou HTTP {resposta.status_code}.',
            repetivel=resposta.status_code == 429 or resposta.status_code >= 500,
        )
