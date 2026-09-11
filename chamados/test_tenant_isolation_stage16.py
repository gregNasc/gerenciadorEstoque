from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from chamados.models import Chamado, ChamadoAnexo, ChamadoMensagem
from chamados.lider_service import InventarioLiderService
from chamados.policies import ChamadoAccessPolicy
from chamados.policies import GruposChamados
from chamados.routing import websocket_urlpatterns
from chamados.services import ChamadoService
from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Perfil,
    RelacionamentoEmpresa,
)
from insumos.models import Cliente, Inventario


class Stage16TenantIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company_a = Empresa.objects.create(nome='Empresa A Etapa 16')
        cls.company_b = Empresa.objects.create(nome='Empresa B Secreta Etapa 16')
        cls.base_a = Base.objects.create(
            empresa=cls.company_a, nome='Base A Etapa 16'
        )
        cls.base_b = Base.objects.create(
            empresa=cls.company_b, nome='Base B Secreta Etapa 16'
        )
        cls.admin_a = cls._admin('admin.a.etapa16', cls.company_a)
        cls.admin_b = cls._admin('admin.b.etapa16', cls.company_b)
        cls.opener_a = cls._operator('abertura.a.etapa16', cls.company_a, cls.base_a)
        cls.opener_b = cls._operator('abertura.b.etapa16', cls.company_b, cls.base_b)
        cls.ticket_a = cls._ticket(
            'CH-E16-A', cls.company_a, cls.base_a, cls.opener_a,
            'Chamado permitido da empresa A',
        )
        cls.ticket_b = cls._ticket(
            'CH-E16-B', cls.company_b, cls.base_b, cls.opener_b,
            'SEGREDO-TENANT-B-ETAPA-16',
        )
        cls.attachment_b = ChamadoAnexo.objects.create(
            chamado=cls.ticket_b,
            arquivo='chamados/teste/segredo-b.txt',
            nome_original='segredo-b.txt',
            enviado_por=cls.opener_b,
        )

    @staticmethod
    def _admin(username, company):
        user = User.objects.create_user(username, password='Teste123!')
        user.perfil.role = Perfil.Role.ADMIN
        user.perfil.empresa = company
        user.perfil.save()
        return user

    @staticmethod
    def _operator(username, company, base):
        user = User.objects.create_user(username, password='Teste123!')
        user.perfil.role = Perfil.Role.OPERADOR
        user.perfil.empresa = company
        user.perfil.save()
        user.perfil.regionais.add(base)
        return user

    @staticmethod
    def _ticket(protocol, company, base, opener, title):
        return Chamado.objects.create(
            protocolo=protocol,
            empresa=company,
            base=base,
            titulo=title,
            descricao='Teste de isolamento da Etapa 16.',
            aberto_por=opener,
        )

    def test_admin_sees_only_own_company_in_queue_dashboard_and_details(self):
        self.assertEqual(
            set(ChamadoAccessPolicy.bases(self.admin_a)),
            {self.base_a},
        )
        self.assertEqual(
            set(ChamadoAccessPolicy.queryset(self.admin_a)),
            {self.ticket_a},
        )

        self.client.force_login(self.admin_a)
        queue = self.client.get(reverse('chamados:lista'))
        dashboard = self.client.get(reverse('chamados:dashboard'))
        external_detail = self.client.get(
            reverse('chamados:detalhe', args=[self.ticket_b.pk])
        )

        self.assertEqual(queue.status_code, 200)
        self.assertEqual(dashboard.status_code, 200)
        self.assertNotContains(queue, 'SEGREDO-TENANT-B-ETAPA-16')
        self.assertEqual(external_detail.status_code, 404)

    def test_view_capability_does_not_grant_attendance_or_export(self):
        relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a,
            empresa_destino=self.company_b,
        )
        self.admin_a.perfil.empresas_acesso_adicional.add(self.company_b)
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relationship,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            acao=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
        )

        self.assertIn(self.ticket_b, ChamadoAccessPolicy.queryset(self.admin_a))
        self.assertNotIn(
            self.ticket_b,
            ChamadoAccessPolicy.queryset(
                self.admin_a,
                action=ChamadoAccessPolicy.ATTEND,
            ),
        )
        self.assertNotIn(
            self.ticket_b,
            ChamadoAccessPolicy.queryset(
                self.admin_a,
                action=ChamadoAccessPolicy.EXPORT,
            ),
        )
        internal_note = ChamadoMensagem.objects.create(
            chamado=self.ticket_b,
            autor=self.admin_b,
            texto='NOTA INTERNA SECRETA DO TENANT B',
            nota_interna=True,
        )
        self.client.force_login(self.admin_a)
        detail = self.client.get(
            reverse('chamados:detalhe', args=[self.ticket_b.pk])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, internal_note.texto)
        self.assertFalse(detail.context['pode_atender'])

        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relationship,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            acao=CapacidadeRelacionamentoEmpresa.Acao.ATENDER,
        )
        self.assertIn(
            self.ticket_b,
            ChamadoAccessPolicy.queryset(
                self.admin_a,
                action=ChamadoAccessPolicy.ATTEND,
            ),
        )

    def test_external_admin_is_not_candidate_or_notification_recipient(self):
        self.assertIn(
            self.admin_a,
            ChamadoAccessPolicy.atendentes_para(self.ticket_a),
        )
        self.assertNotIn(
            self.admin_b,
            ChamadoAccessPolicy.atendentes_para(self.ticket_a),
        )

        notice = ChamadoService._comunicar(
            self.ticket_a,
            self.opener_a,
            'Atualização do chamado A',
            'Mensagem restrita ao tenant A.',
            incluir_fila=True,
        )
        self.assertTrue(notice.usuarios.filter(pk=self.admin_a.pk).exists())
        self.assertFalse(notice.usuarios.filter(pk=self.admin_b.pk).exists())

    def test_forged_external_actions_and_attachment_return_404(self):
        self.client.force_login(self.admin_a)
        message = self.client.post(
            reverse('chamados:mensagem', args=[self.ticket_b.pk]),
            {'texto': 'Tentativa externa', 'nota_interna': 'on'},
        )
        assume = self.client.post(
            reverse('chamados:assumir', args=[self.ticket_b.pk])
        )
        attachment = self.client.get(
            reverse('chamados:baixar_anexo', args=[self.attachment_b.pk])
        )

        self.assertEqual(message.status_code, 404)
        self.assertEqual(assume.status_code, 404)
        self.assertEqual(attachment.status_code, 404)
        self.assertFalse(self.ticket_b.mensagens.exists())

    def test_service_rejects_opening_on_external_base(self):
        client = Cliente.objects.create(sigla='E16', nome='Cliente Etapa 16')
        inventory_b = Inventario.objects.create(
            cliente=client,
            loja='Loja B',
            base=self.base_b,
            data_inicio=timezone.localdate(),
            criado_por=self.opener_b,
        )
        with self.assertRaises(PermissionDenied):
            ChamadoService.abrir(
                usuario=self.admin_a,
                base=self.base_b,
                inventario=inventory_b,
                categoria_equipamento='Sistema',
                titulo='Tentativa de abertura externa',
                descricao='Não deve ser criada.',
            )

    def test_leader_links_and_aliases_cannot_cross_tenants(self):
        client = Cliente.objects.create(sigla='L16', nome='Cliente Líder Etapa 16')
        inventory_b = Inventario.objects.create(
            cliente=client,
            loja='Loja Líder B',
            base=self.base_b,
            data_inicio=timezone.localdate(),
            criado_por=self.opener_b,
        )

        with self.assertRaises(PermissionDenied):
            InventarioLiderService.vincular(
                inventory_b,
                self.opener_a,
                self.admin_a,
                'Tentativa entre tenants.',
            )
        with self.assertRaises(PermissionDenied):
            InventarioLiderService.cadastrar_alias(
                usuario=self.opener_b,
                alias='Alias externo Etapa 16',
                autor=self.admin_a,
            )


class Stage16WebSocketTenantIsolationTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.company_a = Empresa.objects.create(nome='Empresa WS A Etapa 16')
        self.company_b = Empresa.objects.create(nome='Empresa WS B Etapa 16')
        self.company_support = Empresa.objects.create(
            nome='Empresa própria do suporte WS Etapa 16'
        )
        self.base_a = Base.objects.create(empresa=self.company_a, nome='Base WS A')
        self.base_support = Base.objects.create(
            empresa=self.company_support, nome='Base própria do suporte WS'
        )
        self.admin_a = Stage16TenantIsolationTests._admin(
            'admin.ws.a.etapa16', self.company_a
        )
        self.admin_b = Stage16TenantIsolationTests._admin(
            'admin.ws.b.etapa16', self.company_b
        )
        relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a,
            empresa_destino=self.company_b,
            compartilha_suporte_chamados=True,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relationship,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            acao=CapacidadeRelacionamentoEmpresa.Acao.ATENDER,
        )
        self.support = Stage16TenantIsolationTests._operator(
            'suporte.ws.etapa16', self.company_support, self.base_support
        )
        self.support.groups.add(
            Group.objects.get_or_create(name=GruposChamados.SUPORTE)[0]
        )
        self.ticket_a = Stage16TenantIsolationTests._ticket(
            'CH-E16-WS-A', self.company_a, self.base_a, self.admin_a,
            'Evento WebSocket do tenant A',
        )

    def test_event_is_delivered_to_own_admin_but_not_external_admin(self):
        async def scenario():
            application = URLRouter(websocket_urlpatterns)
            own = WebsocketCommunicator(application, '/ws/chamados/presenca/')
            own.scope['user'] = self.admin_a
            external = WebsocketCommunicator(application, '/ws/chamados/presenca/')
            external.scope['user'] = self.admin_b
            support = WebsocketCommunicator(application, '/ws/chamados/presenca/')
            support.scope['user'] = self.support

            self.assertTrue((await own.connect())[0])
            self.assertTrue((await external.connect())[0])
            self.assertTrue((await support.connect())[0])

            await database_sync_to_async(ChamadoService._evento)(
                self.ticket_a,
                'ABERTURA',
                'CHAMADO ABERTO NO TENANT A.',
                self.admin_a,
            )

            received = await own.receive_json_from(timeout=3)
            support_received = await support.receive_json_from(timeout=3)
            self.assertEqual(received['tipo'], 'chamado_evento')
            self.assertEqual(received['evento']['empresa_id'], self.company_a.pk)
            self.assertEqual(support_received['tipo'], 'chamado_evento')
            self.assertEqual(
                support_received['evento']['empresa_id'], self.company_a.pk
            )
            self.assertTrue(await external.receive_nothing(timeout=0.4))

            await own.disconnect()
            await external.disconnect()
            await support.disconnect()

        async_to_sync(scenario)()
