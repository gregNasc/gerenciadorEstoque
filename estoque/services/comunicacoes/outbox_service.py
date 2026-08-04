from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from estoque.models import ComunicadoEntrega

from .providers import DisabledWhatsAppProvider, obter_provedor


class OutboxService:
    @classmethod
    def processar(cls, *, canal=ComunicadoEntrega.Canal.WHATSAPP, limit=100):
        agora = timezone.now()
        with transaction.atomic():
            entregas = list(
                ComunicadoEntrega.objects.select_for_update(skip_locked=True).filter(
                    canal=canal,
                    status__in=[ComunicadoEntrega.Status.PENDENTE, ComunicadoEntrega.Status.FALHA],
                ).filter(
                    Q(proxima_tentativa_em__isnull=True) | Q(proxima_tentativa_em__lte=agora)
                ).order_by('criada_em')[:limit]
            )
            for entrega in entregas:
                entrega.status = ComunicadoEntrega.Status.PROCESSANDO
                entrega.processada_em = agora
            ComunicadoEntrega.objects.bulk_update(entregas, ['status', 'processada_em'])

        provedor = obter_provedor()
        processadas = []
        for entrega in entregas:
            if isinstance(provedor, DisabledWhatsAppProvider):
                cls._marcar_ignorada(entrega.pk, 'Provedor WhatsApp desabilitado.')
                processadas.append(entrega.pk)
                continue
            resultado = provedor.enviar_template(
                destino=entrega.destino,
                template_codigo=entrega.template_codigo,
                idioma=entrega.parametros.get('idioma', 'pt-br').replace('-', '_'),
                parametros={k: v for k, v in entrega.parametros.items() if k != 'idioma'},
                idempotency_key=str(entrega.idempotency_key),
            )
            cls._persistir_resultado(entrega.pk, resultado)
            processadas.append(entrega.pk)
        return processadas

    @staticmethod
    def _marcar_ignorada(entrega_id, motivo):
        ComunicadoEntrega.objects.filter(pk=entrega_id).update(
            status=ComunicadoEntrega.Status.IGNORADA,
            ultimo_erro=motivo,
            processada_em=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def _persistir_resultado(entrega_id, resultado):
        entrega = ComunicadoEntrega.objects.select_for_update().get(pk=entrega_id)
        if entrega.status in (
            ComunicadoEntrega.Status.ENVIADA,
            ComunicadoEntrega.Status.ENTREGUE,
            ComunicadoEntrega.Status.LIDA,
        ):
            return entrega
        agora = timezone.now()
        entrega.tentativas += 1
        entrega.processada_em = agora
        if resultado.sucesso:
            entrega.status = ComunicadoEntrega.Status.ENVIADA
            entrega.provider_message_id = resultado.provider_message_id
            entrega.enviada_em = agora
            entrega.ultimo_erro = ''
            entrega.proxima_tentativa_em = None
        else:
            entrega.ultimo_erro = resultado.erro[:4000]
            limite = settings.WHATSAPP_MAX_RETRIES
            if resultado.repetivel and entrega.tentativas < limite:
                entrega.status = ComunicadoEntrega.Status.FALHA
                espera = settings.WHATSAPP_RETRY_BASE_SECONDS * (2 ** (entrega.tentativas - 1))
                entrega.proxima_tentativa_em = agora + timedelta(seconds=espera)
            else:
                entrega.status = ComunicadoEntrega.Status.FALHA
                entrega.proxima_tentativa_em = None
        entrega.save(update_fields=[
            'status', 'tentativas', 'processada_em', 'provider_message_id',
            'enviada_em', 'ultimo_erro', 'proxima_tentativa_em',
        ])
        return entrega

