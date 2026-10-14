import base64
import hashlib
import hmac
import json

import httpx
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from estoque import test_itens_custodia_r2e as r2e_tests
from estoque.models import (
    Colaborador,
    Custodia,
    ItemCustodia,
    ItemDevolucaoCustodia,
)
from estoque.services.custodia_devolucao_service import CustodiaDevolucaoService
from estoque.services.termo_entrega_custodia_service import (
    TermoEntregaCustodiaService,
)
from integracao.clients.docusign import DocusignClient
from integracao.exceptions import DocusignConfigurationError
from integracao.models import (
    DocusignEnvelope,
    DocusignEvent,
    DocusignTenantConfig,
)
from integracao.services.docusign_service import DocusignService


TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'private': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}


class FakeDocusignClient:
    def __init__(self):
        self.create_calls = []
        self.download_calls = []

    def create_envelope(self, *, account_id, payload):
        self.create_calls.append((account_id, payload))
        return {
            'envelopeId': '11111111-2222-3333-4444-555555555555',
            'uri': '/envelopes/11111111-2222-3333-4444-555555555555',
            'status': 'sent',
        }

    def download_document(self, *, account_id, envelope_id, document_id):
        self.download_calls.append((account_id, envelope_id, document_id))
        return b'%PDF-1.4\n' + document_id.encode() + b'\n%%EOF'


@override_settings(
    STORAGES=TEST_STORAGES,
    APP_BASE_URL='https://estoque.example.test',
    DOCUSIGN_ACCOUNT_ID='account-123',
    DOCUSIGN_WEBHOOK_HMAC_SECRET='webhook-secret',
)
class DocusignR2KTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        r2e_tests.ItensCustodiaR2ETests.setUpTestData.__func__(cls)
        cls.colaborador.email = 'colaborador@example.com'
        cls.colaborador.save()
        ItemCustodia.objects.create(
            custodia=cls.custodia,
            equipamento=cls.equipamento,
            condicao_entrega=Custodia.CondicaoGeral.BOM,
        )
        cls.termo = TermoEntregaCustodiaService.gerar(
            custodia=cls.custodia,
            usuario=cls.usuario,
        )
        cls.config = DocusignTenantConfig.objects.create(
            empresa=cls.empresa,
            habilitada=True,
            nome_testemunha_rh='SETOR DE RH',
            email_testemunha_rh='rh@example.com',
        )

    def test_envio_mapeia_signatario_testemunha_e_persiste_envelope(self):
        fake = FakeDocusignClient()
        envelope = DocusignService.enviar_termo(
            termo=self.termo,
            usuario=self.usuario,
            client=fake,
        )

        self.assertEqual(envelope.status, DocusignEnvelope.Status.ENVIADO)
        self.assertEqual(envelope.empresa, self.empresa)
        self.assertEqual(envelope.termo_entrega, self.termo)
        self.assertEqual(len(envelope.participantes), 2)
        account_id, payload = fake.create_calls[0]
        self.assertEqual(account_id, 'account-123')
        self.assertEqual(
            payload['recipients']['signers'][0]['email'],
            'colaborador@example.com',
        )
        self.assertEqual(
            payload['recipients']['witnesses'][0]['email'],
            'rh@example.com',
        )
        self.assertNotIn('PIN', str(payload))
        self.assertNotIn('PUK', str(payload))

    def test_envio_e_idempotente(self):
        fake = FakeDocusignClient()
        first = DocusignService.enviar_termo(
            termo=self.termo, usuario=self.usuario, client=fake,
        )
        second = DocusignService.enviar_termo(
            termo=self.termo, usuario=self.usuario, client=fake,
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(len(fake.create_calls), 1)
        self.assertEqual(DocusignEnvelope.objects.count(), 1)

    def test_termo_de_devolucao_gera_envelope_proprio(self):
        recebedor = Colaborador.objects.create(
            empresa=self.empresa,
            base=self.base,
            nome='Recebedor RH',
            email='recebedor@example.com',
        )
        item = self.custodia.itens.get()
        devolucao = CustodiaDevolucaoService.registrar(
            custodia=self.custodia,
            itens=[{
                'item_custodia': item,
                'situacao': ItemDevolucaoCustodia.Situacao.DEVOLVIDO,
                'condicao_devolucao': Custodia.CondicaoGeral.BOM,
            }],
            motivo='Encerramento da custódia',
            responsavel_recebimento=recebedor,
            registrado_por=self.usuario,
        )
        envelope = DocusignService.enviar_termo(
            termo=devolucao.termo_devolucao,
            usuario=self.usuario,
            client=FakeDocusignClient(),
        )
        self.assertEqual(
            envelope.tipo_documento,
            DocusignEnvelope.TipoDocumento.DEVOLUCAO,
        )
        self.assertEqual(envelope.termo_devolucao, devolucao.termo_devolucao)
        self.assertIsNone(envelope.termo_entrega)

    def test_empresa_precisa_habilitar_e_configurar_rh(self):
        self.config.habilitada = False
        self.config.save()
        with self.assertRaises(DocusignConfigurationError):
            DocusignService.enviar_termo(
                termo=self.termo,
                usuario=self.usuario,
                client=FakeDocusignClient(),
            )

        self.config.habilitada = True
        self.config.email_testemunha_rh = ''
        with self.assertRaises(ValidationError):
            self.config.save()

    def test_colaborador_sem_email_nao_e_enviado(self):
        self.colaborador.email = ''
        self.colaborador.save()
        with self.assertRaises(DocusignConfigurationError):
            DocusignService.enviar_termo(
                termo=self.termo,
                usuario=self.usuario,
                client=FakeDocusignClient(),
            )

    def test_webhook_concluido_e_idempotente_e_arquiva_documentos(self):
        fake = FakeDocusignClient()
        envelope = DocusignService.enviar_termo(
            termo=self.termo, usuario=self.usuario, client=fake,
        )
        payload = {
            'event': 'envelope-completed',
            'generatedDateTime': '2026-10-08T15:00:00Z',
            'data': {
                'envelopeId': envelope.envelope_id,
                'envelopeSummary': {
                    'status': 'completed',
                    'documentPDFs': [{'PDFBytes': 'nao-deve-ser-persistido'}],
                },
            },
        }
        raw = json.dumps(payload, separators=(',', ':')).encode()
        event, created = DocusignService.processar_webhook(
            raw_body=raw, payload=payload, client=fake,
        )
        same_event, created_again = DocusignService.processar_webhook(
            raw_body=raw, payload=payload, client=fake,
        )

        envelope.refresh_from_db()
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(event.pk, same_event.pk)
        self.assertEqual(envelope.status, DocusignEnvelope.Status.CONCLUIDO)
        self.assertTrue(envelope.pdf_assinado.name)
        self.assertTrue(envelope.certificado.name)
        self.assertEqual(len(envelope.pdf_assinado_sha256), 64)
        self.assertEqual(len(envelope.certificado_sha256), 64)
        self.assertNotIn('documentPDFs', event.payload['data']['envelopeSummary'])
        self.assertEqual(DocusignEvent.objects.count(), 1)
        self.assertEqual(len(fake.download_calls), 2)

    def test_webhook_http_rejeita_hmac_invalido(self):
        response = self.client.post(
            reverse('integracao:docusign_webhook'),
            data=b'{}',
            content_type='application/json',
            HTTP_X_DOCUSIGN_SIGNATURE_1='invalid',
        )
        self.assertEqual(response.status_code, 401)

    def test_webhook_http_aceita_evento_assinado_e_idempotente(self):
        envelope = DocusignService.enviar_termo(
            termo=self.termo,
            usuario=self.usuario,
            client=FakeDocusignClient(),
        )
        payload = {
            'event': 'envelope-delivered',
            'generatedDateTime': '2026-10-08T14:00:00Z',
            'data': {
                'envelopeId': envelope.envelope_id,
                'envelopeSummary': {'status': 'delivered'},
            },
        }
        raw = json.dumps(payload, separators=(',', ':')).encode()
        signature = base64.b64encode(hmac.new(
            b'webhook-secret', raw, hashlib.sha256,
        ).digest()).decode()
        url = reverse('integracao:docusign_webhook')
        first = self.client.post(
            url, data=raw, content_type='application/json',
            HTTP_X_DOCUSIGN_SIGNATURE_1=signature,
        )
        second = self.client.post(
            url, data=raw, content_type='application/json',
            HTTP_X_DOCUSIGN_SIGNATURE_1=signature,
        )
        envelope.refresh_from_db()
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()['created'])
        self.assertFalse(second.json()['created'])
        self.assertEqual(envelope.status, DocusignEnvelope.Status.ENTREGUE)

    def test_evento_atrasado_nao_regride_envelope_concluido(self):
        fake = FakeDocusignClient()
        envelope = DocusignService.enviar_termo(
            termo=self.termo, usuario=self.usuario, client=fake,
        )
        completed = {
            'event': 'envelope-completed',
            'generatedDateTime': '2026-10-08T15:00:00Z',
            'data': {
                'envelopeId': envelope.envelope_id,
                'envelopeSummary': {'status': 'completed'},
            },
        }
        delivered = {
            'event': 'envelope-delivered',
            'generatedDateTime': '2026-10-08T14:00:00Z',
            'data': {
                'envelopeId': envelope.envelope_id,
                'envelopeSummary': {'status': 'delivered'},
            },
        }
        for payload in (completed, delivered):
            raw = json.dumps(payload, separators=(',', ':')).encode()
            DocusignService.processar_webhook(
                raw_body=raw, payload=payload, client=fake,
            )
        envelope.refresh_from_db()
        self.assertEqual(envelope.status, DocusignEnvelope.Status.CONCLUIDO)

    def test_modelo_bloqueia_cruzamento_de_tenant(self):
        other = type(self.empresa).objects.create(nome='Outra Empresa')
        envelope = DocusignEnvelope(
            empresa=other,
            custodia=self.custodia,
            termo_entrega=self.termo,
            tipo_documento=DocusignEnvelope.TipoDocumento.ENTREGA,
            idempotency_key='cross-tenant',
            criado_por=self.usuario,
        )
        with self.assertRaises(ValidationError):
            envelope.full_clean()


class DocusignClientR2KTests(TestCase):
    def test_desabilitado_falha_fechado(self):
        with self.assertRaises(DocusignConfigurationError):
            DocusignClient(enabled=False)

    @override_settings(
        DOCUSIGN_ENABLED=True,
        DOCUSIGN_AUTH_SERVER='https://account-d.docusign.com',
        DOCUSIGN_ESIGN_BASE_URL='https://demo.docusign.net/restapi',
    )
    def test_cliente_jwt_cria_envelope_sem_expor_chave(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == '/oauth/token':
                return httpx.Response(200, json={
                    'access_token': 'access-token', 'expires_in': 3600,
                })
            return httpx.Response(201, json={
                'envelopeId': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                'status': 'sent',
            })

        http = httpx.Client(transport=httpx.MockTransport(handler))
        client = DocusignClient(
            integration_key='integration-key',
            user_id='user-id',
            private_key=pem,
            http_client=http,
            max_retries=0,
        )
        result = client.create_envelope(
            account_id='account-123', payload={'status': 'sent'},
        )
        self.assertEqual(result['status'], 'sent')
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[1].headers['Authorization'], 'Bearer access-token')
        serialized = b''.join(request.content for request in requests)
        self.assertNotIn(pem.encode(), serialized)
