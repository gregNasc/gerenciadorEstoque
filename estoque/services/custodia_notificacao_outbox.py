from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from estoque.models import EntregaNotificacaoCustodia
from estoque.services.comunicacoes.providers import (
    DisabledWhatsAppProvider,
    obter_provedor,
)
from estoque.services.comunicacoes.templates import construir_payload
from integracao.scopes import IntegrationExecutionScope


class CustodiaNotificacaoOutbox:
    @classmethod
    def processar(cls, *, canal=None, limit=100, email_sender=None, whatsapp_provider=None):
        channels = [canal] if canal else [
            EntregaNotificacaoCustodia.Canal.EMAIL,
            EntregaNotificacaoCustodia.Canal.WHATSAPP,
        ]
        now = timezone.now()
        timeout = now - timedelta(
            seconds=settings.CUSTODIA_NOTIFICATION_PROCESSING_TIMEOUT_SECONDS,
        )
        with transaction.atomic():
            EntregaNotificacaoCustodia.objects.filter(
                canal__in=channels,
                status=EntregaNotificacaoCustodia.Status.PROCESSANDO,
                processada_em__lte=timeout,
            ).update(
                status=EntregaNotificacaoCustodia.Status.FALHA,
                proxima_tentativa_em=now,
                ultimo_erro='Processamento anterior expirou e foi reagendado.',
            )
            deliveries = list(
                EntregaNotificacaoCustodia.objects.select_related(
                    'notificacao__empresa',
                ).select_for_update(skip_locked=True).filter(
                    canal__in=channels,
                    status__in=(
                        EntregaNotificacaoCustodia.Status.PENDENTE,
                        EntregaNotificacaoCustodia.Status.FALHA,
                    ),
                ).filter(
                    Q(proxima_tentativa_em__isnull=True)
                    | Q(proxima_tentativa_em__lte=now)
                ).order_by('criada_em')[:limit]
            )
            for delivery in deliveries:
                delivery.status = EntregaNotificacaoCustodia.Status.PROCESSANDO
                delivery.processada_em = now
            EntregaNotificacaoCustodia.objects.bulk_update(
                deliveries, ('status', 'processada_em'),
            )
        processed = []
        for delivery in deliveries:
            try:
                if delivery.canal == EntregaNotificacaoCustodia.Canal.EMAIL:
                    cls._send_email(delivery, sender=email_sender)
                    result = (True, '', '', {}, False)
                else:
                    result = cls._send_whatsapp(
                        delivery, provider=whatsapp_provider,
                    )
            except Exception:
                result = (
                    False,
                    'Falha interna isolada ao enviar a notificação.',
                    '',
                    {},
                    True,
                )
            cls._persist_result(delivery.pk, *result)
            processed.append(delivery.pk)
        return processed

    @staticmethod
    def _send_email(delivery, *, sender=None):
        notification = delivery.notificacao
        message = EmailMultiAlternatives(
            subject=notification.titulo,
            body=notification.mensagem,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[delivery.destino],
        )
        send = sender or message.send
        sent = send() if sender is None else send(message)
        if sent != 1:
            raise RuntimeError('O provedor de e-mail não confirmou o envio.')

    @staticmethod
    def _send_whatsapp(delivery, *, provider=None):
        provider = provider or obter_provedor()
        if isinstance(provider, DisabledWhatsAppProvider):
            return (False, 'Provedor WhatsApp desabilitado.', '', {}, False)
        parameters = delivery.parametros
        declared = parameters.get('_integration_scope') or {}
        scope = IntegrationExecutionScope(
            kind=declared.get('kind'),
            source=declared.get('source'),
            company_id=declared.get('company_id'),
        )
        payload = construir_payload(
            template_codigo=delivery.template_codigo,
            idioma=parameters.get('idioma'),
            parametros=parameters,
        )
        result = provider.enviar_payload(
            destino=delivery.destino,
            payload=payload,
            idempotency_key=delivery.idempotency_key,
            execution_scope=scope,
        )
        return (
            result.sucesso,
            result.erro,
            result.provider_message_id,
            result.resposta,
            result.repetivel,
        )

    @staticmethod
    @transaction.atomic
    def _persist_result(
        delivery_id, success, error, provider_message_id, response, repeatable,
    ):
        delivery = EntregaNotificacaoCustodia.objects.select_for_update().get(
            pk=delivery_id,
        )
        if delivery.status in {
            EntregaNotificacaoCustodia.Status.ENVIADA,
            EntregaNotificacaoCustodia.Status.ENTREGUE,
        }:
            return delivery
        now = timezone.now()
        delivery.tentativas += 1
        delivery.processada_em = now
        delivery.provider_resposta = CustodiaNotificacaoOutbox._sanitize_response(
            response or {},
        )
        if success:
            delivery.status = EntregaNotificacaoCustodia.Status.ENVIADA
            delivery.enviada_em = now
            delivery.provider_message_id = provider_message_id or ''
            delivery.ultimo_erro = ''
            delivery.proxima_tentativa_em = None
        else:
            delivery.status = EntregaNotificacaoCustodia.Status.FALHA
            delivery.ultimo_erro = (error or 'Falha de entrega.')[:4000]
            if (
                repeatable
                and delivery.tentativas < settings.CUSTODIA_NOTIFICATION_MAX_RETRIES
            ):
                wait = settings.CUSTODIA_NOTIFICATION_RETRY_BASE_SECONDS * (
                    2 ** (delivery.tentativas - 1)
                )
                delivery.proxima_tentativa_em = now + timedelta(seconds=wait)
            else:
                delivery.proxima_tentativa_em = None
        delivery.save(update_fields=(
            'status', 'tentativas', 'processada_em', 'provider_resposta',
            'enviada_em', 'provider_message_id', 'ultimo_erro',
            'proxima_tentativa_em',
        ))
        return delivery

    @classmethod
    def _sanitize_response(cls, value):
        sensitive = ('authorization', 'password', 'senha', 'token', 'secret')
        if isinstance(value, dict):
            return {
                key: cls._sanitize_response(item)
                for key, item in value.items()
                if not any(part in str(key).casefold() for part in sensitive)
            }
        if isinstance(value, list):
            return [cls._sanitize_response(item) for item in value]
        return value
