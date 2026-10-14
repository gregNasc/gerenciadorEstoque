import base64
import hashlib
import hmac
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from integracao.exceptions import DocusignError, DocusignWebhookError
from integracao.services.docusign_service import DocusignService


MAX_WEBHOOK_BYTES = 1024 * 1024


def valid_docusign_hmac(raw_body, signatures, secret):
    if isinstance(signatures, str):
        signatures = [signatures]
    if not signatures or not secret:
        return False
    expected = base64.b64encode(
        hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
    ).decode('ascii')
    return any(
        hmac.compare_digest(expected, signature.strip())
        for signature in signatures if signature
    )


@csrf_exempt
@require_POST
def docusign_webhook(request):
    raw_body = request.body
    if len(raw_body) > MAX_WEBHOOK_BYTES:
        return JsonResponse({'detail': 'Payload excede o limite.'}, status=413)
    signatures = [
        value for name, value in request.headers.items()
        if name.lower().startswith('x-docusign-signature-')
    ]
    if not valid_docusign_hmac(
        raw_body, signatures, settings.DOCUSIGN_WEBHOOK_HMAC_SECRET,
    ):
        return JsonResponse({'detail': 'Assinatura inválida.'}, status=401)
    try:
        payload = json.loads(raw_body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'detail': 'JSON inválido.'}, status=400)
    try:
        _event, created = DocusignService.processar_webhook(
            raw_body=raw_body,
            payload=payload,
        )
    except DocusignWebhookError:
        return JsonResponse({'detail': 'Evento não reconhecido.'}, status=202)
    except DocusignError:
        return JsonResponse({'detail': 'Falha temporária.'}, status=503)
    return JsonResponse({'received': True, 'created': created})
