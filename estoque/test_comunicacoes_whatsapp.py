from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from estoque.models import Comunicado, ComunicadoEntrega, Empresa
from estoque.services.comunicacoes.consentimento_service import WhatsAppConsentimentoService
from estoque.services.comunicacoes.dispatcher import ComunicacaoDispatcher
from estoque.services.comunicacoes.outbox_service import OutboxService
from estoque.services.comunicacoes.phone import normalizar_whatsapp, whatsapp_valido
from estoque.services.comunicacoes.providers.base import ProviderResult
from estoque.services.comunicacoes.templates import TemplatePayloadError, construir_payload


class WhatsAppComunicacaoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa WhatsApp')
        self.user = User.objects.create_user('usuario-whatsapp', password='teste')
        self.user.perfil.empresa = self.empresa
        self.user.perfil.save(update_fields=['empresa'])

    def comunicado(self, template='auditoria_aberta'):
        comunicado = Comunicado.objects.create(
            titulo='Aviso',
            mensagem='Mensagem operacional',
            criado_por=self.user,
            empresa=self.empresa,
            url='/auditorias/1/',
            dados={'template_codigo': template},
        )
        comunicado.usuarios.add(self.user)
        return comunicado

    def test_normaliza_numero_brasileiro_sem_duplicar_ddi(self):
        self.assertEqual(normalizar_whatsapp('(14) 99999-9999'), '5514999999999')
        self.assertEqual(normalizar_whatsapp('+55 14 99999-9999'), '5514999999999')
        self.assertTrue(whatsapp_valido('5514999999999'))

    def test_consentimento_e_revogacao_preservam_historico(self):
        perfil = WhatsAppConsentimentoService.ativar(
            self.user.perfil,
            numero='(14) 99999-9999',
            origem='Portal usuário',
        )
        self.assertTrue(perfil.whatsapp_ativo)
        consentido_em = perfil.whatsapp_consentimento_em
        perfil = WhatsAppConsentimentoService.revogar(perfil)
        self.assertFalse(perfil.whatsapp_ativo)
        self.assertEqual(perfil.whatsapp_consentimento_em, consentido_em)
        self.assertIsNotNone(perfil.whatsapp_revogado_em)

    @override_settings(WHATSAPP_ENABLED=True, WHATSAPP_PROVIDER='meta')
    def test_dispatcher_sempre_cria_sistema_e_ignora_template_desconhecido(self):
        WhatsAppConsentimentoService.ativar(
            self.user.perfil, numero='14999999999', origem='TESTE'
        )
        comunicado = self.comunicado('nao_existe')
        ComunicacaoDispatcher.criar_entregas(comunicado.pk)
        self.assertTrue(comunicado.entregas.filter(canal='SISTEMA', status='ENTREGUE').exists())
        externa = comunicado.entregas.get(canal='WHATSAPP')
        self.assertEqual(externa.status, ComunicadoEntrega.Status.IGNORADA)
        self.assertIn('NÃO CADASTRADO', externa.ultimo_erro)

    @override_settings(APP_BASE_URL='https://estoque.example.com', DEBUG=False)
    def test_payload_deterministico_separa_corpo_botao_e_idioma(self):
        payload = construir_payload(
            template_codigo='auditoria_aberta',
            idioma='en',
            parametros={'titulo': 'Título', 'mensagem': '', 'url': '/auditorias/1/'},
        )
        template = payload['template']
        self.assertEqual(template['language']['code'], 'en_US')
        self.assertEqual(template['components'][0]['parameters'][1]['text'], '-')
        self.assertEqual(
            template['components'][1]['parameters'][0]['text'],
            'https://estoque.example.com/auditorias/1/',
        )

    @override_settings(APP_BASE_URL='http://inseguro.example.com', DEBUG=False)
    def test_payload_exige_https_em_producao(self):
        with self.assertRaises(TemplatePayloadError):
            construir_payload(
                template_codigo='auditoria_aberta',
                idioma='pt-br',
                parametros={'titulo': 'A', 'mensagem': 'B', 'url': '/'},
            )

    @override_settings(
        APP_BASE_URL='https://estoque.example.com',
        DEBUG=False,
        WHATSAPP_PROVIDER='meta',
        WHATSAPP_PROCESSING_TIMEOUT_SECONDS=60,
    )
    @patch('estoque.services.comunicacoes.outbox_service.obter_provedor')
    def test_outbox_recupera_travada_e_isola_falha_por_entrega(self, obter):
        provedor = obter.return_value
        provedor.enviar_payload.side_effect = [
            RuntimeError('falha isolada'),
            ProviderResult(sucesso=True, provider_message_id='wamid.2'),
        ]
        agora = timezone.now()
        for indice, status in enumerate(('PROCESSANDO', 'PENDENTE'), start=1):
            ComunicadoEntrega.objects.create(
                comunicado=self.comunicado(),
                usuario=self.user,
                canal='WHATSAPP',
                status=status,
                destino='5514999999999',
                template_codigo='auditoria_aberta',
                parametros={'titulo': 'A', 'mensagem': 'B', 'url': '/', 'idioma': 'pt-br'},
                processada_em=agora - timedelta(minutes=2) if status == 'PROCESSANDO' else None,
            )
        OutboxService.processar(limit=10)
        status = list(ComunicadoEntrega.objects.filter(canal='WHATSAPP').order_by('id').values_list('status', flat=True))
        self.assertEqual(status, ['FALHA', 'ENVIADA'])

    def test_preferencias_exigem_login_e_permite_ativar_revogar(self):
        self.assertEqual(self.client.get('/perfil/comunicacoes/').status_code, 302)
        self.client.force_login(self.user)
        self.client.post('/perfil/comunicacoes/', {'acao': 'ativar', 'numero': '14999999999'})
        self.user.perfil.refresh_from_db()
        self.assertTrue(self.user.perfil.whatsapp_ativo)
        self.client.post('/perfil/comunicacoes/', {'acao': 'revogar'})
        self.user.perfil.refresh_from_db()
        self.assertFalse(self.user.perfil.whatsapp_ativo)
