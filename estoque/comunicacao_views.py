import hashlib
import hmac
import json
import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import ComunicadoArquivo, ComunicadoEntrega
from .services.comunicacoes.consentimento_service import WhatsAppConsentimentoService
from .services.comunicacoes.phone import mascarar_whatsapp


@login_required
def baixar_arquivo_comunicado(request, arquivo_id):
    perfil = getattr(request.user, 'perfil', None)
    empresa_id = perfil.empresa_id if perfil else None
    escopo = ComunicadoArquivo.objects.select_related('comunicado').filter(
        Q(comunicado__enviar_para_todos=True)
        | Q(comunicado__usuarios=request.user)
        | Q(comunicado__empresa_id=empresa_id)
    ).distinct()
    arquivo = get_object_or_404(escopo, pk=arquivo_id)
    nome = Path(arquivo.arquivo.name).name
    content_type = mimetypes.guess_type(nome)[0] or 'application/octet-stream'
    return FileResponse(
        arquivo.arquivo.open('rb'),
        as_attachment=True,
        filename=nome,
        content_type=content_type,
    )


@login_required
def preferencias_whatsapp(request):
    perfil = request.user.perfil
    if request.method == 'POST':
        acao = request.POST.get('acao')
        try:
            if acao == 'ativar':
                WhatsAppConsentimentoService.ativar(
                    perfil,
                    numero=request.POST.get('numero', ''),
                    origem='PORTAL_USUARIO',
                )
                messages.success(request, 'WhatsApp ativado com consentimento registrado.')
            elif acao == 'revogar':
                WhatsAppConsentimentoService.revogar(perfil)
                messages.success(request, 'Consentimento do WhatsApp revogado.')
            else:
                messages.error(request, 'Ação inválida.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
        return redirect('estoque:preferencias_whatsapp')
    perfil.refresh_from_db()
    return render(request, 'estoque/preferencias_whatsapp.html', {
        'perfil': perfil,
        'numero_mascarado': mascarar_whatsapp(perfil.whatsapp_numero),
    })


def _assinatura_valida(request):
    if not settings.WHATSAPP_WEBHOOK_APP_SECRET:
        return False
    recebida = request.headers.get('X-Hub-Signature-256', '')
    esperada = 'sha256=' + hmac.new(
        settings.WHATSAPP_WEBHOOK_APP_SECRET.encode(),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(recebida, esperada)


@csrf_exempt
def whatsapp_webhook(request):
    if request.method == 'GET':
        if (
            settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
            and
            request.GET.get('hub.mode') == 'subscribe'
            and hmac.compare_digest(
                request.GET.get('hub.verify_token', ''),
                settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN,
            )
        ):
            return HttpResponse(request.GET.get('hub.challenge', ''))
        return HttpResponse(status=403)
    if request.method != 'POST':
        return HttpResponse(status=405)
    if not _assinatura_valida(request):
        return HttpResponse(status=403)
    try:
        payload = json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return JsonResponse({'ok': True})

    mapa = {
        'sent': ComunicadoEntrega.Status.ENVIADA,
        'delivered': ComunicadoEntrega.Status.ENTREGUE,
        'read': ComunicadoEntrega.Status.LIDA,
        'failed': ComunicadoEntrega.Status.FALHA,
    }
    agora = timezone.now()
    for entrada in payload.get('entry', []):
        for alteracao in entrada.get('changes', []):
            for status in alteracao.get('value', {}).get('statuses', []):
                novo = mapa.get(status.get('status'))
                if not novo:
                    continue
                entrega = ComunicadoEntrega.objects.filter(
                    provider_message_id=status.get('id', '')
                ).first()
                if not entrega:
                    continue
                ordem = {
                    ComunicadoEntrega.Status.ENVIADA: 1,
                    ComunicadoEntrega.Status.ENTREGUE: 2,
                    ComunicadoEntrega.Status.LIDA: 3,
                }
                if novo == ComunicadoEntrega.Status.FALHA and entrega.status in {
                    ComunicadoEntrega.Status.ENTREGUE,
                    ComunicadoEntrega.Status.LIDA,
                }:
                    continue
                if novo != ComunicadoEntrega.Status.FALHA and ordem.get(novo, 0) < ordem.get(entrega.status, 0):
                    continue
                entrega.status = novo
                campos = ['status']
                if novo == ComunicadoEntrega.Status.ENVIADA and not entrega.enviada_em:
                    entrega.enviada_em = agora
                    campos.append('enviada_em')
                elif novo == ComunicadoEntrega.Status.ENTREGUE:
                    entrega.entregue_em = agora
                    campos.append('entregue_em')
                elif novo == ComunicadoEntrega.Status.LIDA:
                    entrega.lida_em = agora
                    campos.append('lida_em')
                elif novo == ComunicadoEntrega.Status.FALHA:
                    entrega.ultimo_erro = 'Falha informada pelo webhook do provedor.'
                    campos.append('ultimo_erro')
                entrega.save(update_fields=campos)
    return JsonResponse({'ok': True})
