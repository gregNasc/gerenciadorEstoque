from datetime import date, timedelta

from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from chamados.routing import websocket_urlpatterns
from estoque.models import (
    Base,
    DeclaracaoCorreios,
    Emprestimo,
    Empresa,
    GrupoRegional,
    Modulo,
    Perfil,
)
from estoque.services.assistente_operacional_service import AssistenteOperacionalService
from estoque.tenant_features import TenantFeatureService
from estoque.tenant_scope import TenantScope


def tenant_admin(username, company):
    user = User.objects.create_user(username)
    user.perfil.role = Perfil.Role.ADMIN
    user.perfil.empresa = company
    user.perfil.save()
    return user


class TenantFeatureEnforcementStage22Tests(TestCase):
    def setUp(self):
        self.company_a = Empresa.objects.create(
            nome='Empresa Features 22 A',
            slug='empresa-features-22-a',
        )
        self.company_b = Empresa.objects.create(
            nome='Empresa Features 22 B',
            slug='empresa-features-22-b',
        )
        self.admin_a = tenant_admin('admin_features_22_a', self.company_a)
        self.admin_b = tenant_admin('admin_features_22_b', self.company_b)
        self.superuser = User.objects.create_superuser(
            username='superuser_features_22',
            email='superuser-features-22@example.test',
            password='senha-apenas-teste-22',
        )

    def disable(self, company, code):
        return TenantFeatureService.configure(
            tenant=company,
            codigo=code,
            enabled=False,
            actor=self.superuser,
        )

    def test_disabled_feature_disappears_from_navigation_and_scripts(self):
        self.disable(self.company_a, Modulo.Codigo.CHAMADOS)
        self.disable(self.company_a, Modulo.Codigo.TORY)
        self.client.force_login(self.admin_a)

        response = self.client.get(reverse('estoque:index'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="chamadosDropdown"')
        self.assertNotContains(response, '/ws/chamados/presenca/')
        self.assertNotContains(response, 'id="tory-widget"')
        self.assertNotContains(response, '/static/js/tory.js')

    def test_navigation_removes_every_disabled_operational_group(self):
        for code in (
            Modulo.Codigo.ESTOQUE,
            Modulo.Codigo.EQUIPAMENTOS,
            Modulo.Codigo.INSUMOS,
            Modulo.Codigo.CHECKLIST,
            Modulo.Codigo.TRANSFERENCIAS,
            Modulo.Codigo.EMPRESTIMOS,
            Modulo.Codigo.SICK,
        ):
            self.disable(self.company_a, code)
        self.client.force_login(self.admin_a)

        response = self.client.get(reverse('estoque:caixa_comunicados'))

        self.assertEqual(response.status_code, 200)
        for element_id in (
            'checklistDropdown',
            'navbarEstoque',
            'dropdownSolicitacoes',
            'transferenciasDropdown',
            'cadastrosDropdown',
        ):
            self.assertNotContains(response, f'id="{element_id}"')
        self.assertNotContains(response, '>Dashboard de Ativos<')
        self.assertNotContains(response, '>SICK<')

    def test_direct_page_and_ajax_are_blocked_in_backend(self):
        self.disable(self.company_a, Modulo.Codigo.CHAMADOS)
        self.client.force_login(self.admin_a)

        self.assertEqual(
            self.client.get(reverse('chamados:lista')).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse('chamados:equipamentos_por_categoria'),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            ).status_code,
            403,
        )

    def test_unnamed_api_endpoint_is_blocked_by_namespace(self):
        self.disable(self.company_a, Modulo.Codigo.INSUMOS)
        self.client.force_login(self.admin_a)

        response = self.client.get('/insumos/api/kpis/inventarios/')

        self.assertEqual(response.status_code, 403)

    def test_equipment_ajax_and_direct_object_url_are_blocked(self):
        self.disable(self.company_a, Modulo.Codigo.EQUIPAMENTOS)
        self.client.force_login(self.admin_a)

        self.assertEqual(
            self.client.get(reverse('estoque:detalhes_produto', args=(999999,))).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse('estoque:detalhes_regional_api', args=(999999,)),
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            ).status_code,
            403,
        )

    def test_catalog_and_service_order_namespaces_are_blocked(self):
        self.disable(self.company_a, Modulo.Codigo.CATALOGO)
        self.disable(self.company_a, Modulo.Codigo.ORDENS_SERVICO)
        self.client.force_login(self.admin_a)

        self.assertEqual(
            self.client.get(reverse('compras:catalogo_empresa')).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse('ordens_servico:lista')).status_code,
            403,
        )

    def test_combined_dashboard_requires_supplies_and_equipment_features(self):
        self.disable(self.company_a, Modulo.Codigo.EQUIPAMENTOS)
        self.client.force_login(self.admin_a)

        self.assertEqual(
            self.client.get(reverse('insumos:dashboard_saude_geral')).status_code,
            403,
        )

    def test_equipment_dashboard_hides_combined_view_without_supplies(self):
        self.disable(self.company_a, Modulo.Codigo.INSUMOS)
        self.client.force_login(self.admin_a)

        response = self.client.get(reverse('insumos:dashboard_saude_equipamentos'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse('insumos:dashboard_saude_geral'),
        )

    def test_integration_namespace_is_blocked_with_supplies_disabled(self):
        self.disable(self.company_a, Modulo.Codigo.INSUMOS)
        self.client.force_login(self.admin_a)

        self.assertEqual(
            self.client.get(reverse('integracao:planning_mappings')).status_code,
            403,
        )

    def test_shared_declaration_route_uses_its_actual_operation_feature(self):
        group = GrupoRegional.objects.create(nome='Grupo Feature 22')
        origin = Base.objects.create(
            nome='Origem Feature 22',
            empresa=self.company_a,
            grupo_regional=group,
        )
        destination = Base.objects.create(
            nome='Destino Feature 22',
            empresa=self.company_a,
            grupo_regional=group,
        )
        loan = Emprestimo.objects.create(
            protocolo='EMP-FEATURE-22',
            grupo=group,
            regional_origem=origin,
            regional_destino=destination,
            solicitado_por=self.admin_a,
            motivo='Validação da flag do domínio real',
            data_emprestimo=date.today(),
            data_prevista_devolucao=date.today() + timedelta(days=7),
        )
        declaration = DeclaracaoCorreios.objects.create(
            tipo_operacao=DeclaracaoCorreios.TipoOperacao.EMPRESTIMO,
            emprestimo=loan,
            gerada_por=self.admin_a,
        )
        self.disable(self.company_a, Modulo.Codigo.TRANSFERENCIAS)
        self.client.force_login(self.admin_a)

        url = reverse('estoque:declaracao_detalhe', args=(declaration.pk,))
        self.assertEqual(self.client.get(url).status_code, 200)

        self.disable(self.company_a, Modulo.Codigo.EMPRESTIMOS)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_disabling_one_tenant_does_not_affect_another(self):
        self.disable(self.company_a, Modulo.Codigo.CHAMADOS)

        self.client.force_login(self.admin_b)
        response = self.client.get(reverse('chamados:lista'))

        self.assertEqual(response.status_code, 200)

    def test_superuser_bypasses_tenant_feature_gate(self):
        self.disable(self.company_a, Modulo.Codigo.CHAMADOS)
        self.client.force_login(self.superuser)

        response = self.client.get(reverse('chamados:lista'))

        self.assertEqual(response.status_code, 200)

    def test_tory_itself_and_queried_domain_are_both_enforced(self):
        scope = TenantScope.fresh_for_user(self.admin_a)
        self.disable(self.company_a, Modulo.Codigo.EQUIPAMENTOS)

        with self.assertRaises(PermissionDenied):
            AssistenteOperacionalService.responder(
                self.admin_a,
                'Liste todos os equipamentos cadastrados',
                tenant_scope=scope,
            )

        TenantFeatureService.configure(
            tenant=self.company_a,
            codigo=Modulo.Codigo.EQUIPAMENTOS,
            enabled=True,
            actor=self.superuser,
        )
        self.disable(self.company_a, Modulo.Codigo.TORY)
        with self.assertRaises(PermissionDenied):
            AssistenteOperacionalService.responder(
                self.admin_a,
                'Olá, Tory',
                tenant_scope=TenantScope.fresh_for_user(self.admin_a),
            )


class TenantFeatureWebSocketStage22Tests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.company = Empresa.objects.create(
            nome='Empresa WebSocket Features 22',
            slug='empresa-websocket-features-22',
        )
        self.user = tenant_admin('usuario_ws_features_22', self.company)
        root = User.objects.create_superuser(
            username='root_ws_features_22',
            email='root-ws-features-22@example.test',
            password='senha-apenas-teste-ws-22',
        )
        TenantFeatureService.configure(
            tenant=self.company,
            codigo=Modulo.Codigo.CHAMADOS,
            enabled=False,
            actor=root,
        )

    def test_presence_socket_rejects_tenant_with_calls_disabled(self):
        async def scenario():
            application = URLRouter(websocket_urlpatterns)
            communicator = WebsocketCommunicator(
                application,
                '/ws/chamados/presenca/',
            )
            communicator.scope['user'] = self.user
            connected, code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4403)

        async_to_sync(scenario)()
