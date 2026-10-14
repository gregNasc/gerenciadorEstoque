import hashlib
import json
import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from estoque.models import TermoDevolucaoCustodia, TermoEntregaCustodia
from integracao.clients.docusign import DocusignClient
from integracao.exceptions import (
    DocusignConfigurationError,
    DocusignError,
    DocusignWebhookError,
)
from integracao.mappers.docusign import (
    DocusignEnvelopeMapper,
    DocusignWebhookMapper,
)
from integracao.models import (
    DocusignEnvelope,
    DocusignEvent,
    DocusignTenantConfig,
)


logger = logging.getLogger('integracao.docusign')


class DocusignService:
    STATUS_MAP = {
        'envelope-sent': DocusignEnvelope.Status.ENVIADO,
        'sent': DocusignEnvelope.Status.ENVIADO,
        'envelope-delivered': DocusignEnvelope.Status.ENTREGUE,
        'delivered': DocusignEnvelope.Status.ENTREGUE,
        'recipient-completed': DocusignEnvelope.Status.ASSINADO,
        'signed': DocusignEnvelope.Status.ASSINADO,
        'envelope-completed': DocusignEnvelope.Status.CONCLUIDO,
        'completed': DocusignEnvelope.Status.CONCLUIDO,
        'envelope-declined': DocusignEnvelope.Status.RECUSADO,
        'declined': DocusignEnvelope.Status.RECUSADO,
        'envelope-voided': DocusignEnvelope.Status.ANULADO,
        'voided': DocusignEnvelope.Status.ANULADO,
    }
    STATUS_RANK = {
        DocusignEnvelope.Status.PREPARANDO: 0,
        DocusignEnvelope.Status.ERRO: 0,
        DocusignEnvelope.Status.ENVIADO: 1,
        DocusignEnvelope.Status.ENTREGUE: 2,
        DocusignEnvelope.Status.ASSINADO: 3,
        DocusignEnvelope.Status.CONCLUIDO: 4,
        DocusignEnvelope.Status.RECUSADO: 4,
        DocusignEnvelope.Status.ANULADO: 4,
    }

    @classmethod
    def enviar_termo(cls, *, termo, usuario, client=None):
        if not usuario or not usuario.is_active:
            raise DocusignConfigurationError('O usuário responsável deve estar ativo.')
        custodia, tipo, relation = cls._term_context(termo)
        try:
            config = DocusignTenantConfig.objects.get(
                empresa_id=custodia.empresa_id,
                habilitada=True,
            )
        except DocusignTenantConfig.DoesNotExist as exc:
            raise DocusignConfigurationError(
                'DocuSign não está habilitado para esta empresa.'
            ) from exc
        account_id = config.conta_id or settings.DOCUSIGN_ACCOUNT_ID
        if not account_id:
            raise DocusignConfigurationError(
                'A conta DocuSign não foi configurada para esta empresa.'
            )
        idempotency_key = f'docusign:{tipo.lower()}:{termo.pk}:v{termo.versao}'
        defaults = {
            'empresa': custodia.empresa,
            'custodia': custodia,
            'tipo_documento': tipo,
            'criado_por': usuario,
            relation: termo,
        }
        try:
            with transaction.atomic():
                envelope, created = DocusignEnvelope.objects.select_for_update().get_or_create(
                    idempotency_key=idempotency_key,
                    defaults=defaults,
                )
        except IntegrityError:
            envelope = DocusignEnvelope.objects.get(idempotency_key=idempotency_key)
            created = False
        if envelope.envelope_id:
            return envelope
        payload, participants = DocusignEnvelopeMapper.build(
            termo=termo,
            config=config,
            idempotency_key=idempotency_key,
        )
        owns_client = client is None
        api = client or DocusignClient()
        try:
            response = api.create_envelope(account_id=account_id, payload=payload)
        except DocusignError as exc:
            DocusignEnvelope.objects.filter(pk=envelope.pk).update(
                status=DocusignEnvelope.Status.ERRO,
                ultima_falha=type(exc).__name__,
                atualizado_em=timezone.now(),
            )
            raise
        finally:
            if owns_client:
                api.close()
        now = timezone.now()
        with transaction.atomic():
            envelope = DocusignEnvelope.objects.select_for_update().get(pk=envelope.pk)
            if not envelope.envelope_id:
                envelope.envelope_id = str(response['envelopeId']).strip()
                envelope.status = DocusignEnvelope.Status.ENVIADO
                envelope.participantes = participants
                envelope.provider_metadata = {
                    'uri': response.get('uri', ''),
                    'status': response.get('status', 'sent'),
                }
                envelope.enviado_em = now
                envelope.ultima_falha = ''
                envelope.save()
        logger.info(
            'docusign_envelope_sent envelope=%s company=%s type=%s',
            envelope.envelope_id, envelope.empresa_id, envelope.tipo_documento,
        )
        from estoque.models import EventoNotificacaoCustodia
        from estoque.services.custodia_notificacao_service import (
            CustodiaNotificacaoService,
        )

        CustodiaNotificacaoService.publicar(
            evento=EventoNotificacaoCustodia.Evento.TERMO_ENVIADO,
            custodia=envelope.custodia,
            criado_por=envelope.criado_por,
            termo_entrega=envelope.termo_entrega,
            termo_devolucao=envelope.termo_devolucao,
            envelope_docusign=envelope,
        )
        return envelope

    @classmethod
    def processar_webhook(cls, *, raw_body, payload, client=None):
        mapped = DocusignWebhookMapper.parse(payload)
        payload_sha = hashlib.sha256(raw_body).hexdigest()
        event_identity = '|'.join((
            mapped['envelope_id'], mapped['event_type'],
            str(mapped['occurred_at'] or ''), payload_sha,
        ))
        event_key = hashlib.sha256(event_identity.encode()).hexdigest()
        existing = DocusignEvent.objects.filter(event_key=event_key).first()
        if existing:
            return existing, False
        try:
            envelope = DocusignEnvelope.objects.select_related(
                'empresa__configuracao_docusign',
            ).get(provider='DOCUSIGN', envelope_id=mapped['envelope_id'])
        except DocusignEnvelope.DoesNotExist as exc:
            raise DocusignWebhookError(
                'Envelope DocuSign não pertence ao sistema.'
            ) from exc
        new_status = cls.STATUS_MAP.get(
            mapped['event_type'].lower(),
            cls.STATUS_MAP.get(mapped['status'].lower()),
        )
        signed_pdf = certificate = None
        if new_status == DocusignEnvelope.Status.CONCLUIDO and not envelope.pdf_assinado:
            try:
                config = envelope.empresa.configuracao_docusign
            except DocusignTenantConfig.DoesNotExist as exc:
                raise DocusignConfigurationError(
                    'Configuração DocuSign da empresa não encontrada.'
                ) from exc
            account_id = config.conta_id or settings.DOCUSIGN_ACCOUNT_ID
            owns_client = client is None
            api = client or DocusignClient()
            try:
                signed_pdf = api.download_document(
                    account_id=account_id,
                    envelope_id=envelope.envelope_id,
                    document_id='combined',
                )
                certificate = api.download_document(
                    account_id=account_id,
                    envelope_id=envelope.envelope_id,
                    document_id='certificate',
                )
            finally:
                if owns_client:
                    api.close()
        status_advanced = False
        with transaction.atomic():
            envelope = DocusignEnvelope.objects.select_for_update().get(pk=envelope.pk)
            event, created = DocusignEvent.objects.get_or_create(
                event_key=event_key,
                defaults={
                    'envelope': envelope,
                    'event_type': mapped['event_type'],
                    'status': mapped['status'],
                    'ocorrido_em': mapped['occurred_at'],
                    'payload_sha256': payload_sha,
                    'payload': mapped['payload'],
                },
            )
            if not created:
                return event, False
            if new_status and cls._pode_avancar_status(envelope.status, new_status):
                status_advanced = envelope.status != new_status
                envelope.status = new_status
                event_time = mapped['occurred_at'] or timezone.now()
                if new_status == DocusignEnvelope.Status.ASSINADO:
                    envelope.assinado_em = envelope.assinado_em or event_time
                if new_status == DocusignEnvelope.Status.CONCLUIDO:
                    envelope.assinado_em = envelope.assinado_em or event_time
                    envelope.concluido_em = envelope.concluido_em or event_time
            if signed_pdf and not envelope.pdf_assinado:
                envelope.pdf_assinado.save(
                    'termo-assinado.pdf', ContentFile(signed_pdf), save=False,
                )
                envelope.pdf_assinado_sha256 = hashlib.sha256(signed_pdf).hexdigest()
            if certificate and not envelope.certificado:
                envelope.certificado.save(
                    'certificado.pdf', ContentFile(certificate), save=False,
                )
                envelope.certificado_sha256 = hashlib.sha256(certificate).hexdigest()
            envelope.ultima_falha = ''
            envelope.save()
        if status_advanced and new_status in {
            DocusignEnvelope.Status.ASSINADO,
            DocusignEnvelope.Status.CONCLUIDO,
        }:
            from estoque.models import EventoNotificacaoCustodia
            from estoque.services.custodia_notificacao_service import (
                CustodiaNotificacaoService,
            )

            notification_event = (
                EventoNotificacaoCustodia.Evento.TERMO_ASSINADO
                if new_status == DocusignEnvelope.Status.ASSINADO
                else EventoNotificacaoCustodia.Evento.TERMO_CONCLUIDO
            )
            CustodiaNotificacaoService.publicar(
                evento=notification_event,
                custodia=envelope.custodia,
                criado_por=envelope.criado_por,
                termo_entrega=envelope.termo_entrega,
                termo_devolucao=envelope.termo_devolucao,
                envelope_docusign=envelope,
            )
        logger.info(
            'docusign_webhook_processed envelope=%s event=%s status=%s',
            envelope.envelope_id, mapped['event_type'], envelope.status,
        )
        return event, True

    @classmethod
    def _pode_avancar_status(cls, atual, novo):
        terminais = {
            DocusignEnvelope.Status.CONCLUIDO,
            DocusignEnvelope.Status.RECUSADO,
            DocusignEnvelope.Status.ANULADO,
        }
        if atual in terminais:
            return atual == novo
        return cls.STATUS_RANK.get(novo, 0) >= cls.STATUS_RANK.get(atual, 0)

    @staticmethod
    def _term_context(termo):
        if isinstance(termo, TermoEntregaCustodia):
            return (
                termo.custodia,
                DocusignEnvelope.TipoDocumento.ENTREGA,
                'termo_entrega',
            )
        if isinstance(termo, TermoDevolucaoCustodia):
            return (
                termo.devolucao.custodia,
                DocusignEnvelope.TipoDocumento.DEVOLUCAO,
                'termo_devolucao',
            )
        raise DocusignConfigurationError('Tipo de termo não suportado.')
