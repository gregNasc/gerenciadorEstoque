import base64
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.utils.dateparse import parse_datetime

from estoque.models import TermoDevolucaoCustodia, TermoEntregaCustodia
from integracao.exceptions import DocusignConfigurationError, DocusignWebhookError


class DocusignEnvelopeMapper:
    @classmethod
    def build(cls, *, termo, config, idempotency_key):
        custodia = cls._custodia(termo)
        # Releia a pessoa no momento do envio. Termos e Custódias podem estar
        # em cache em processos longos, mas nome/e-mail precisam refletir a
        # configuração vigente quando o envelope é criado.
        colaborador = type(custodia.colaborador).objects.get(
            pk=custodia.colaborador_id,
        )
        if not colaborador.email:
            raise DocusignConfigurationError(
                'O colaborador da Custódia precisa ter e-mail para assinar.'
            )
        if not config.email_testemunha_rh:
            raise DocusignConfigurationError(
                'O e-mail da testemunha de RH não foi configurado para a empresa.'
            )
        with termo.arquivo_pdf.open('rb') as source:
            encoded_document = base64.b64encode(source.read()).decode('ascii')
        is_delivery = isinstance(termo, TermoEntregaCustodia)
        document_label = 'Termo de Entrega' if is_delivery else 'Termo de Devolução'
        filename = Path(termo.arquivo_pdf.name).name or 'termo-custodia.pdf'
        app_url = settings.APP_BASE_URL.rstrip('/')
        if urlparse(app_url).scheme != 'https':
            raise DocusignConfigurationError(
                'APP_BASE_URL deve usar HTTPS para receber webhooks DocuSign.'
            )
        webhook_url = f'{app_url}/integracao/docusign/webhook/'
        payload = {
            'emailSubject': f'{document_label} de ativos em custódia',
            'emailBlurb': (
                'Revise e assine o termo de ativos em custódia. '
                'Após a assinatura do colaborador, o RH participará como testemunha.'
            ),
            'documents': [{
                'documentBase64': encoded_document,
                'name': filename,
                'fileExtension': 'pdf',
                'documentId': '1',
            }],
            'recipients': {
                'signers': [{
                    'email': colaborador.email,
                    'name': colaborador.nome,
                    'recipientId': '1',
                    'routingOrder': '1',
                    'tabs': {
                        'signHereTabs': [{
                            'anchorString': 'ASSINATURA DO COLABORADOR',
                            'anchorUnits': 'pixels',
                            'anchorXOffset': '5',
                            'anchorYOffset': '18',
                        }],
                    },
                }],
                'witnesses': [{
                    'email': config.email_testemunha_rh,
                    'name': config.nome_testemunha_rh,
                    'recipientId': '2',
                    'routingOrder': '2',
                    'witnessFor': '1',
                    'tabs': {
                        'signHereTabs': [{
                            'anchorString': 'TESTEMUNHA - DEPARTAMENTO PESSOAL',
                            'anchorUnits': 'pixels',
                            'anchorXOffset': '5',
                            'anchorYOffset': '18',
                        }],
                    },
                }],
            },
            'customFields': {
                'textCustomFields': [
                    {'name': 'idempotency_key', 'value': idempotency_key},
                    {'name': 'empresa_id', 'value': str(custodia.empresa_id)},
                ],
            },
            'eventNotification': {
                'url': webhook_url,
                'deliveryMode': 'SIM',
                'loggingEnabled': 'true',
                'requireAcknowledgment': 'true',
                'includeDocuments': 'false',
                'includeHMAC': 'true',
                'envelopeEvents': [
                    {'envelopeEventStatusCode': status}
                    for status in ('sent', 'delivered', 'completed', 'declined', 'voided')
                ],
                'recipientEvents': [
                    {'recipientEventStatusCode': status}
                    for status in ('Delivered', 'Completed', 'Declined')
                ],
            },
            'status': 'sent',
        }
        participants = [
            {
                'role': 'SIGNATARIO',
                'name': colaborador.nome,
                'email': colaborador.email,
                'routing_order': 1,
            },
            {
                'role': 'TESTEMUNHA_RH',
                'name': config.nome_testemunha_rh,
                'email': config.email_testemunha_rh,
                'routing_order': 2,
            },
        ]
        return payload, participants

    @staticmethod
    def _custodia(termo):
        if isinstance(termo, TermoEntregaCustodia):
            return termo.custodia
        if isinstance(termo, TermoDevolucaoCustodia):
            return termo.devolucao.custodia
        raise DocusignConfigurationError('Tipo de termo não suportado pelo DocuSign.')


class DocusignWebhookMapper:
    SENSITIVE_TOKENS = (
        'authorization', 'password', 'token', 'secret', 'documentpdf',
        'pdfbytes', 'documentbase64',
    )

    @classmethod
    def parse(cls, payload):
        if not isinstance(payload, dict):
            raise DocusignWebhookError('Payload DocuSign inválido.')
        data = payload.get('data') or {}
        summary = data.get('envelopeSummary') or {}
        envelope_id = str(
            data.get('envelopeId') or summary.get('envelopeId') or ''
        ).strip()
        event_type = str(payload.get('event') or '').strip()
        status = str(summary.get('status') or data.get('status') or '').strip()
        occurred_raw = payload.get('generatedDateTime') or data.get('timestamp')
        occurred_at = parse_datetime(occurred_raw) if occurred_raw else None
        if not envelope_id or not event_type:
            raise DocusignWebhookError(
                'Evento DocuSign sem envelope ou tipo de evento.'
            )
        return {
            'envelope_id': envelope_id,
            'event_type': event_type,
            'status': status,
            'occurred_at': occurred_at,
            'payload': cls._sanitize(payload),
        }

    @classmethod
    def _sanitize(cls, value):
        if isinstance(value, dict):
            return {
                key: cls._sanitize(item)
                for key, item in value.items()
                if not any(token in key.lower() for token in cls.SENSITIVE_TOKENS)
            }
        if isinstance(value, list):
            return [cls._sanitize(item) for item in value]
        return value
