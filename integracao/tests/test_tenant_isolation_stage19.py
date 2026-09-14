from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from estoque.models import Base, Comunicado, Empresa, Perfil
from estoque.services.comunicacoes.dispatcher import ComunicacaoDispatcher
from estoque.services.assistente_operacional_service import InterpretacaoOperacional
from estoque.services.portal_assistant_service import InventoryPortalAssistantService
from estoque.tenant_scope import TenantScope
from insumos.models import CategoriaInsumo, Cliente, Insumo, Inventario
from insumos.services.preco_online_service import PrecoOnlineErro, PrecoOnlineService
from integracao.clients.inventory_portal import PortalInventorySummary
from integracao.models import InventoryPlanningSyncRun
from integracao.scopes import IntegrationExecutionScope, IntegrationScopeError
from integracao.services.inventory_planning_service import InventoryPlanningService


class _EmptyPlanningClient:
    def iter_pages(self, endpoint, *, params=None):
        yield [], {"page": 1, "pageCount": 1, "total": 0}, {}


class Stage19IntegrationTenantIsolationTests(TestCase):
    def setUp(self):
        self.company_a = Empresa.objects.create(nome="Empresa Integração A")
        self.company_b = Empresa.objects.create(nome="Empresa Integração B")
        self.base_a = Base.objects.create(nome="Base Integração A", empresa=self.company_a)
        self.base_b = Base.objects.create(nome="Base Integração B", empresa=self.company_b)
        self.admin_a = User.objects.create_user("stage19-admin-a")
        self.admin_a.perfil.role = Perfil.Role.ADMIN
        self.admin_a.perfil.empresa = self.company_a
        self.admin_a.perfil.save()
        self.client_a = Cliente.objects.create(sigla="S19A", nome="Cliente Stage 19 A")
        self.client_b = Cliente.objects.create(sigla="S19B", nome="Cliente Stage 19 B")
        self.day = date(2026, 9, 10)
        Inventario.objects.create(
            cliente=self.client_a,
            loja="10",
            base=self.base_a,
            data_inicio=self.day,
            criado_por=self.admin_a,
        )
        Inventario.objects.create(
            cliente=self.client_b,
            loja="20",
            base=self.base_b,
            data_inicio=self.day,
            criado_por=self.admin_a,
        )

    @staticmethod
    def _portal_row(client, store):
        return PortalInventorySummary(
            portal_id=int(store),
            detail_url=f"https://portal.example/{store}/",
            client_code=client,
            store_number=store,
            store_display=f"{client} {store}",
            inventory_date=date(2026, 9, 10),
        )

    def test_admin_portal_is_filtered_by_local_tenant_even_without_base_filter(self):
        interpretation = InterpretacaoOperacional(
            pergunta="inventários agora",
            texto="inventarios agora",
            intencao="portal_tempo_real",
        )
        visible = InventoryPortalAssistantService._filter_authorized(
            self.admin_a,
            [self._portal_row("S19A", "10"), self._portal_row("S19B", "20")],
            interpretation,
            self.day,
            self.day,
            tenant_scope=TenantScope.fresh_for_user(self.admin_a),
        )

        self.assertEqual([(row.client_code, row.store_number) for row in visible], [("S19A", "10")])

    def test_inventory_export_omits_foreign_client_catalog(self):
        self.client.force_login(self.admin_a)

        response = self.client.get(reverse("insumos:exportar_excel"))

        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        values = list(workbook["Siglas e Tipos"].values)
        flattened = {value for row in values for value in row if value is not None}
        self.assertIn("S19A", flattened)
        self.assertNotIn("S19B", flattened)

    def test_price_search_requires_explicit_authorized_company(self):
        category = CategoriaInsumo.objects.create(nome="Stage 19")
        item = Insumo.objects.create(
            descricao="Item Stage 19",
            categoria=category,
            unidade_medida="UN",
        )

        with self.assertRaises(PrecoOnlineErro):
            PrecoOnlineService.pesquisar(
                insumo=item,
                termo="item stage 19",
                usuario=self.admin_a,
            )
        with self.assertRaises(PrecoOnlineErro):
            PrecoOnlineService.pesquisar(
                insumo=item,
                termo="item stage 19",
                usuario=self.admin_a,
                empresa=self.company_b,
            )

    def test_mapping_permission_does_not_open_global_planning_configuration(self):
        permission = Permission.objects.get(codename="gerenciar_mapeamentos_planning")
        self.admin_a.user_permissions.add(permission)
        self.client.force_login(self.admin_a)

        response = self.client.get(reverse("integracao:planning_mappings"))

        self.assertEqual(response.status_code, 403)

    def test_planning_run_records_explicit_global_scope(self):
        run = InventoryPlanningService(client=_EmptyPlanningClient()).sync_catalog("regions")

        self.assertEqual(run.scope["kind"], "PLATFORM_GLOBAL")
        self.assertEqual(run.scope["source"], "INVENTORY_PLANNING")
        self.assertEqual(InventoryPlanningSyncRun.objects.get(pk=run.pk).scope, run.scope)

    def test_planning_rejects_tenant_scope_for_global_snapshot(self):
        with self.assertRaises(IntegrationScopeError):
            InventoryPlanningService(
                client=_EmptyPlanningClient(),
                execution_scope=IntegrationExecutionScope.tenant(
                    "INVENTORY_PLANNING",
                    self.company_a,
                ),
            )

    @override_settings(WHATSAPP_ENABLED=True, WHATSAPP_PROVIDER="meta")
    def test_whatsapp_delivery_persists_explicit_tenant_scope(self):
        self.admin_a.perfil.whatsapp_ativo = True
        self.admin_a.perfil.whatsapp_numero = "5514999999999"
        self.admin_a.perfil.whatsapp_consentimento_em = timezone.now()
        self.admin_a.perfil.whatsapp_revogado_em = None
        self.admin_a.perfil.save()
        notice = Comunicado.objects.create(
            titulo="Stage 19",
            mensagem="Escopo explícito",
            criado_por=self.admin_a,
            empresa=self.company_a,
            dados={"template_codigo": "auditoria_aberta"},
        )
        notice.usuarios.add(self.admin_a)

        ComunicacaoDispatcher.criar_entregas(notice.pk)

        delivery = notice.entregas.get(canal="WHATSAPP")
        self.assertEqual(
            delivery.parametros["_integration_scope"],
            {
                "kind": "TENANT",
                "source": "WHATSAPP_COMUNICADOS",
                "company_id": self.company_a.pk,
            },
        )

    def test_global_calendar_import_is_identified_and_superuser_only(self):
        self.admin_a.is_staff = True
        self.admin_a.save(update_fields=("is_staff",))
        self.client.force_login(self.admin_a)
        self.assertEqual(self.client.get(reverse("insumos:importar_excel")).status_code, 403)

        superuser = User.objects.create_superuser("stage19-root", password=None)
        self.client.force_login(superuser)
        response = self.client.get(reverse("insumos:importar_excel"))
        self.assertContains(response, "Escopo: plataforma global")
