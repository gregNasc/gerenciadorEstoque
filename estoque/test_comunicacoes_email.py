from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from estoque.models import Comunicado, ComunicadoEntrega, Empresa, Perfil
from estoque.checks import comunicacoes_externas_configuradas
from estoque.services.comunicacoes.dispatcher import ComunicacaoDispatcher
from estoque.services.comunicacoes.outbox_service import OutboxService
from estoque.services.comunicacoes.providers.base import ProviderResult


@override_settings(
    NOTIFICACOES_EMAIL_ENABLED=True,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='nao-responda@example.com',
    APP_BASE_URL='https://estoque.example.com',
)
class EmailComunicacaoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa E-mail')
        self.user = User.objects.create_user(
            'usuario-email',
            email='usuario@example.com',
            password='teste',
        )
        self.user.perfil.empresa = self.empresa
        self.user.perfil.save(update_fields=['empresa'])

    def comunicado(self, *, usuario=None, dados=None):
        usuario = usuario or self.user
        comunicado = Comunicado.objects.create(
            titulo='Ação necessária',
            mensagem='Existe uma atividade pendente.',
            criado_por=self.user,
            empresa=self.empresa,
            url='/solicitacoes/1/',
            dados=dados or {},
        )
        comunicado.usuarios.add(usuario)
        return comunicado

    def test_dispatcher_cria_sistema_e_email_auditavel(self):
        comunicado = self.comunicado()

        entregas = ComunicacaoDispatcher.criar_entregas(comunicado.pk)

        self.assertEqual(len(entregas), 2)
        sistema = comunicado.entregas.get(canal=ComunicadoEntrega.Canal.SISTEMA)
        email = comunicado.entregas.get(canal=ComunicadoEntrega.Canal.EMAIL)
        self.assertEqual(sistema.status, ComunicadoEntrega.Status.ENTREGUE)
        self.assertEqual(email.status, ComunicadoEntrega.Status.PENDENTE)
        self.assertEqual(email.destino, 'usuario@example.com')
        self.assertEqual(email.provedor, 'django-email')
        self.assertEqual(
            email.parametros['_integration_scope']['source'],
            'EMAIL_COMUNICADOS',
        )

    @patch(
        'estoque.services.comunicacoes.outbox_service.obter_provedor',
        side_effect=AssertionError('WhatsApp não pode processar e-mail'),
    )
    def test_processamento_email_nunca_invoca_provedor_whatsapp(self, _whatsapp):
        comunicado = self.comunicado()
        ComunicacaoDispatcher.criar_entregas(comunicado.pk)

        ids = OutboxService.processar(
            canal=ComunicadoEntrega.Canal.EMAIL,
            limit=10,
        )

        entrega = comunicado.entregas.get(canal=ComunicadoEntrega.Canal.EMAIL)
        entrega.refresh_from_db()
        self.assertEqual(ids, [entrega.pk])
        self.assertEqual(entrega.status, ComunicadoEntrega.Status.ENVIADA)
        self.assertEqual(entrega.tentativas, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['usuario@example.com'])
        self.assertIn('https://estoque.example.com/solicitacoes/1/', mail.outbox[0].body)

    @patch('estoque.services.comunicacoes.outbox_service.obter_provedor_email')
    def test_falha_transitoria_de_email_e_reagendada(self, obter_email):
        obter_email.return_value.enviar_payload.return_value = ProviderResult(
            sucesso=False,
            erro='SMTP temporariamente indisponível',
            repetivel=True,
        )
        comunicado = self.comunicado()
        ComunicacaoDispatcher.criar_entregas(comunicado.pk)

        OutboxService.processar(canal=ComunicadoEntrega.Canal.EMAIL)

        entrega = comunicado.entregas.get(canal=ComunicadoEntrega.Canal.EMAIL)
        entrega.refresh_from_db()
        self.assertEqual(entrega.status, ComunicadoEntrega.Status.FALHA)
        self.assertEqual(entrega.tentativas, 1)
        self.assertIsNotNone(entrega.proxima_tentativa_em)
        self.assertNotIn('usuario@example.com', entrega.ultimo_erro)

    def test_email_invalido_fica_ignorado_sem_tentar_envio(self):
        self.user.email = ''
        self.user.save(update_fields=['email'])
        comunicado = self.comunicado()

        ComunicacaoDispatcher.criar_entregas(comunicado.pk)

        entrega = comunicado.entregas.get(canal=ComunicadoEntrega.Canal.EMAIL)
        self.assertEqual(entrega.status, ComunicadoEntrega.Status.IGNORADA)
        self.assertIn('INVÁLIDO', entrega.ultimo_erro)

    def test_jose_nao_recebe_conteudo_financeiro_em_canal_externo(self):
        jose = User.objects.create_user(
            'jose.barboza',
            email='jose@example.com',
            password='teste',
        )
        jose.perfil.empresa = self.empresa
        jose.perfil.role = Perfil.Role.ADMIN
        jose.perfil.save(update_fields=['empresa', 'role'])
        comunicado = self.comunicado(
            usuario=jose,
            dados={'conteudo_financeiro': True},
        )

        ComunicacaoDispatcher.criar_entregas(comunicado.pk)

        self.assertFalse(comunicado.usuarios.filter(pk=jose.pk).exists())
        self.assertFalse(comunicado.entregas.filter(usuario=jose).exists())

    @patch(
        'estoque.management.commands.processar_entregas_comunicados.OutboxService.processar'
    )
    def test_comando_operacional_processa_os_dois_canais(self, processar):
        processar.side_effect = [[101], [202]]
        saida = StringIO()

        call_command(
            'processar_entregas_comunicados',
            canal='TODOS',
            limit=25,
            stdout=saida,
        )

        self.assertEqual(processar.call_count, 2)
        self.assertEqual(
            [chamada.kwargs['canal'] for chamada in processar.call_args_list],
            [ComunicadoEntrega.Canal.EMAIL, ComunicadoEntrega.Canal.WHATSAPP],
        )
        self.assertIn('2 entrega(s) processada(s)', saida.getvalue())

    @override_settings(
        NOTIFICACOES_EMAIL_ENABLED=True,
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST_USER='',
        EMAIL_HOST_PASSWORD='',
    )
    def test_check_bloqueia_ativacao_smtp_incompleta(self):
        erros = comunicacoes_externas_configuradas(None)
        self.assertIn('estoque.E001', {erro.id for erro in erros})
