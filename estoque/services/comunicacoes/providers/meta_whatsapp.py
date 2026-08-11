import re

import requests
from django.conf import settings

from .base import ProviderResult


def _sanitizar_texto(valor):
    texto = str(valor or '')[:2000]
    segredo = settings.WHATSAPP_ACCESS_TOKEN
    if segredo:
        texto = texto.replace(segredo, '[REDACTED]')
    return re.sub(r'Bearer\s+[^\s]+', 'Bearer [REDACTED]', texto, flags=re.IGNORECASE)


def _resposta_segura(dados):
    if not isinstance(dados, dict):
        return {}
    erro = dados.get('error') if isinstance(dados.get('error'), dict) else {}
    return {
        'error': {
            chave: _sanitizar_texto(erro.get(chave))
            for chave in ('message', 'type', 'code', 'error_subcode')
            if erro.get(chave) not in (None, '')
        },
    } if erro else {}


class MetaWhatsAppProvider:
    def enviar_payload(self, *, destino, payload, idempotency_key):
        if not all((settings.WHATSAPP_API_BASE_URL, settings.WHATSAPP_ACCESS_TOKEN, settings.WHATSAPP_PHONE_NUMBER_ID)):
            return ProviderResult(sucesso=False, erro='CONFIGURAÇÃO DO PROVEDOR INCOMPLETA.', repetivel=False)
        if not isinstance(payload, dict) or payload.get('type') != 'template':
            return ProviderResult(sucesso=False, erro='PAYLOAD DO TEMPLATE INVÁLIDO.', repetivel=False)
        payload = {**payload, 'to': destino}
        url = f'{settings.WHATSAPP_API_BASE_URL.rstrip("/")}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages'
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
            try:
                dados = resposta.json() if resposta.content else {}
            except ValueError:
                dados = {}
        except (requests.Timeout, requests.ConnectionError) as exc:
            return ProviderResult(sucesso=False, erro=_sanitizar_texto(exc), repetivel=True)
        except requests.RequestException as exc:
            return ProviderResult(sucesso=False, erro=_sanitizar_texto(exc), repetivel=False)
        seguro = _resposta_segura(dados)
        if 200 <= resposta.status_code < 300:
            mensagens = dados.get('messages') or []
            return ProviderResult(
                sucesso=True,
                provider_message_id=mensagens[0].get('id', '') if mensagens else '',
                resposta=seguro,
            )
        return ProviderResult(
            sucesso=False,
            resposta=seguro,
            erro=f'PROVEDOR RETORNOU HTTP {resposta.status_code}.',
            repetivel=resposta.status_code == 429 or resposta.status_code >= 500,
        )
