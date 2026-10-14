import json

from django.test import TestCase, override_settings
from django.utils import timezone

from estoque import test_itens_custodia_r2e as r2e_tests
from estoque.models import (
    Colaborador,
    ComunicadoEntrega,
    Custodia,
    EntregaNotificacaoCustodia,
    EventoNotificacaoCustodia,
    ItemCustodia,
    ItemDevolucaoCustodia,
    Perfil,
)
from estoque.services.comunicacoes.providers.base import ProviderResult
from estoque.services.custodia_devolucao_service import CustodiaDevolucaoService
from estoque.services.custodia_notificacao_outbox import CustodiaNotificacaoOutbox
from estoque.services.custodia_notificacao_service import CustodiaNotificacaoService
from estoque.services.termo_entrega_custodia_service import (
    TermoEntregaCustodiaService,
)
from integracao.models import DocusignEnvelope, DocusignTenantConfig
from integracao.services.docusign_service import DocusignService


TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'private': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}


class FakeDocusignClient:
    envelope_id = '99999999-8888-7777-6666-555555555555'

    def create_envelope(self, *, account_id, payload):
        return {'envelopeId': self.envelope_id, 'status': 'sent', 'uri': '/envelope'}

    def download_document(self, *, account_id, envelope_id, document_id):
        return b'%PDF-1.4\n' + document_id.encode() + b'\n%%EOF'


class FakeWhatsAppProvider:
    def __init__(self):
        self.calls = []

    def enviar_payload(self, **kwargs):
        self.calls.append(kwargs)
        return ProviderResult(
            sucesso=True,
            provider_message_id='wa-message-1',
            resposta={'accepted': True},
        )


@override_settings(
    STORAGES=TEST_STORAGES,
    APP_BASE_URL='https://estoque.example.test',
    CUSTODIA_EMAIL_ENABLED=False,
    WHATSAPP_ENABLED=False,
    DOCUSIGN_ACCOUNT_ID='account-123',
)
class CustodiaNotificacaoR2LTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        r2e_tests.ItensCustodiaR2ETests.setUpTestData.__func__(cls)
        cls.perfil, _ = Perfil.objects.update_or_create(
            user=cls.usuario,
            defaults={
                'empresa': cls.empresa,
                'role': Perfil.Role.ADMIN,
                'whatsapp_numero': '+5511999990000',
            },
        )
        cls.colaborador.usuario = cls.usuario
        cls.colaborador.email = 'colaborador@example.com'
        cls.colaborador.telefone = '+5511999990000'
        cls.colaborador.save()
        cls.item = ItemCustodia.objects.create(
            custodia=cls.custodia,
            equipamento=cls.equipamento,
            condicao_entrega=Custodia.CondicaoGeral.BOM,
        )
        CustodiaNotificacaoService.publicar(
            evento=EventoNotificacaoCustodia.Evento.CUSTODIA_CRIADA,
            custodia=cls.custodia,
            criado_por=cls.usuario,
        )

    def test_colaborador_sem_user_recebe_evento_e_email_auditavel(self):
        collaborator = Colaborador.objects.create(
            empresa=self.empresa,
            base=self.base,
            nome='Pessoa sem acesso',
            email='pessoa@example.com',
        )
        custody = Custodia.objects.create(
            empresa=self.empresa,
            base=self.base,
            colaborador=collaborator,
            registrado_por=self.usuario,
            status=Custodia.Status.ATIVA,
        )
        event = custody.eventos_notificacao.get(
            evento=EventoNotificacaoCustodia.Evento.CUSTODIA_CRIADA,
        )
        self.assertIsNone(event.comunicado)
        delivery = event.entregas.get(canal=EntregaNotificacaoCustodia.Canal.EMAIL)
        self.assertEqual(delivery.destino, 'pessoa@example.com')
        self.assertEqual(delivery.status, EntregaNotificacaoCustodia.Status.IGNORADA)

    def test_usuario_vinculado_recebe_comunicado_interno(self):
        event = self.custodia.eventos_notificacao.get(
            evento=EventoNotificacaoCustodia.Evento.CUSTODIA_CRIADA,
        )
        self.assertIsNotNone(event.comunicado)
        self.assertTrue(event.comunicado.usuarios.filter(pk=self.usuario.pk).exists())
        self.assertTrue(ComunicadoEntrega.objects.filter(
            comunicado=event.comunicado,
            usuario=self.usuario,
            canal=ComunicadoEntrega.Canal.SISTEMA,
            status=ComunicadoEntrega.Status.ENTREGUE,
        ).exists())
        self.assertTrue(event.entregas.filter(
            canal=EntregaNotificacaoCustodia.Canal.SISTEMA,
            status=EntregaNotificacaoCustodia.Status.ENTREGUE,
        ).exists())

    def test_publicacao_e_idempotente(self):
        first = CustodiaNotificacaoService.publicar(
            evento=EventoNotificacaoCustodia.Evento.CUSTODIA_CRIADA,
            custodia=self.custodia,
            criado_por=self.usuario,
        )
        second = CustodiaNotificacaoService.publicar(
            evento=EventoNotificacaoCustodia.Evento.CUSTODIA_CRIADA,
            custodia=self.custodia,
            criado_por=self.usuario,
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            EventoNotificacaoCustodia.objects.filter(
                custodia=self.custodia,
                evento=EventoNotificacaoCustodia.Evento.CUSTODIA_CRIADA,
            ).count(),
            1,
        )
        self.assertEqual(first.entregas.count(), 2)

    def test_geracao_de_termo_publica_evento_automaticamente(self):
        term = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        event = EventoNotificacaoCustodia.objects.get(
            termo_entrega=term,
            evento=EventoNotificacaoCustodia.Evento.TERMO_GERADO,
        )
        self.assertEqual(event.empresa, self.empresa)
        self.assertNotIn('PIN', str(event.dados))
        self.assertNotIn('PUK', str(event.dados))

    @override_settings(CUSTODIA_EMAIL_ENABLED=True)
    def test_outbox_envia_email_e_registra_tentativa(self):
        term = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        delivery = EntregaNotificacaoCustodia.objects.get(
            notificacao__termo_entrega=term,
            canal=EntregaNotificacaoCustodia.Canal.EMAIL,
        )
        sent = []
        CustodiaNotificacaoOutbox.processar(
            canal=EntregaNotificacaoCustodia.Canal.EMAIL,
            email_sender=lambda message: sent.append(message) or 1,
        )
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EntregaNotificacaoCustodia.Status.ENVIADA)
        self.assertEqual(delivery.tentativas, 1)
        self.assertEqual(sent[0].to, ['colaborador@example.com'])
        self.assertIsNotNone(delivery.enviada_em)

    @override_settings(CUSTODIA_EMAIL_ENABLED=True)
    def test_falha_de_email_e_reagendada_sem_alterar_custodia(self):
        term = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        status_before = self.custodia.status

        def fail(_message):
            raise RuntimeError('provider unavailable')

        CustodiaNotificacaoOutbox.processar(
            canal=EntregaNotificacaoCustodia.Canal.EMAIL,
            email_sender=fail,
        )
        delivery = EntregaNotificacaoCustodia.objects.get(
            notificacao__termo_entrega=term,
            canal=EntregaNotificacaoCustodia.Canal.EMAIL,
        )
        self.custodia.refresh_from_db()
        self.assertEqual(delivery.status, EntregaNotificacaoCustodia.Status.FALHA)
        self.assertEqual(delivery.tentativas, 1)
        self.assertIsNotNone(delivery.proxima_tentativa_em)
        self.assertEqual(self.custodia.status, status_before)

    @override_settings(WHATSAPP_ENABLED=True, WHATSAPP_PROVIDER='meta')
    def test_whatsapp_exige_consentimento_e_preserva_escopo_tenant(self):
        self.perfil.whatsapp_ativo = True
        self.perfil.whatsapp_consentimento_em = timezone.now()
        self.perfil.whatsapp_revogado_em = None
        self.perfil.save()
        term = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        delivery = EntregaNotificacaoCustodia.objects.get(
            notificacao__termo_entrega=term,
            canal=EntregaNotificacaoCustodia.Canal.WHATSAPP,
        )
        provider = FakeWhatsAppProvider()
        CustodiaNotificacaoOutbox.processar(
            canal=EntregaNotificacaoCustodia.Canal.WHATSAPP,
            whatsapp_provider=provider,
        )
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EntregaNotificacaoCustodia.Status.ENVIADA)
        self.assertEqual(provider.calls[0]['execution_scope'].company_id, self.empresa.pk)
        self.assertEqual(provider.calls[0]['idempotency_key'], delivery.idempotency_key)

    def test_sem_consentimento_nao_cria_entrega_whatsapp(self):
        term = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        self.assertFalse(EntregaNotificacaoCustodia.objects.filter(
            notificacao__termo_entrega=term,
            canal=EntregaNotificacaoCustodia.Canal.WHATSAPP,
        ).exists())

    def test_fluxo_docusign_publica_enviado_assinado_e_concluido(self):
        term = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        DocusignTenantConfig.objects.create(
            empresa=self.empresa,
            habilitada=True,
            email_testemunha_rh='rh@example.com',
        )
        api = FakeDocusignClient()
        envelope = DocusignService.enviar_termo(
            termo=term,
            usuario=self.usuario,
            client=api,
        )
        events = (
            ('recipient-completed', 'delivered', '2026-10-09T10:00:00Z'),
            ('envelope-completed', 'completed', '2026-10-09T10:05:00Z'),
        )
        for event_type, status, timestamp in events:
            payload = {
                'event': event_type,
                'generatedDateTime': timestamp,
                'data': {
                    'envelopeId': envelope.envelope_id,
                    'envelopeSummary': {'status': status},
                },
            }
            raw = json.dumps(payload, separators=(',', ':')).encode()
            DocusignService.processar_webhook(
                raw_body=raw,
                payload=payload,
                client=api,
            )
        event_types = set(EventoNotificacaoCustodia.objects.filter(
            envelope_docusign=envelope,
        ).values_list('evento', flat=True))
        self.assertEqual(event_types, {
            EventoNotificacaoCustodia.Evento.TERMO_ENVIADO,
            EventoNotificacaoCustodia.Evento.TERMO_ASSINADO,
            EventoNotificacaoCustodia.Evento.TERMO_CONCLUIDO,
        })

    def test_devolucao_publica_evento_e_termo_separados(self):
        receiver = Colaborador.objects.create(
            empresa=self.empresa,
            base=self.base,
            nome='Recebedor',
        )
        return_record = CustodiaDevolucaoService.registrar(
            custodia=self.custodia,
            itens=[{
                'item_custodia': self.item,
                'situacao': ItemDevolucaoCustodia.Situacao.DEVOLVIDO,
                'condicao_devolucao': Custodia.CondicaoGeral.BOM,
            }],
            motivo='Devolução programada',
            responsavel_recebimento=receiver,
            registrado_por=self.usuario,
        )
        self.assertTrue(EventoNotificacaoCustodia.objects.filter(
            devolucao=return_record,
            evento=EventoNotificacaoCustodia.Evento.DEVOLUCAO_REGISTRADA,
        ).exists())
        self.assertTrue(EventoNotificacaoCustodia.objects.filter(
            termo_devolucao=return_record.termo_devolucao,
            evento=EventoNotificacaoCustodia.Evento.TERMO_GERADO,
        ).exists())
