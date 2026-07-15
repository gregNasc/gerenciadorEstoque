from datetime import datetime, timedelta
from io import StringIO

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.test import Client as HttpClient
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from estoque.models import Base, Empresa, Perfil
from insumos.models import Cliente, Inventario
from integracao.models import (
    InventoryPlanningSyncRun,
    PlanningClient,
    PlanningClientBinding,
    PlanningEvent,
    PlanningInventoryType,
    PlanningOperationalBaseBinding,
    PlanningRegion,
    PlanningRegionBinding,
    PlanningStore,
)
from integracao.repositories.planning_repository import InventoryPlanningRepository
from integracao.services.binding_suggestions import (
    suggest_local_clients,
    suggest_operational_bases,
)
from integracao.services.inventory_planning_service import InventoryPlanningService
from integracao.services.materialization import PlanningEventMaterializer
from integracao.services.operational_base_resolver import OperationalBaseResolver


class BindingResolutionTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.company = Empresa.objects.create(nome="Bindings")
        self.regular_base = Base.objects.create(nome="SP INT CPN", empresa=self.company)
        self.oxxo_base = Base.objects.create(nome="OXXO SP INT CPN X", empresa=self.company)
        self.regular_client = Cliente.objects.create(sigla="BSA", nome="Barbosa")
        self.oxxo_client = Cliente.objects.create(sigla="OXX", nome="Mercado OXXO (Grupo Nós)")
        self.region = self._region("region-cpn", "CAMPINAS")
        self.external_oxxo = self._client("client-oxxo", "MERCADO OXXO")
        self.external_regular = self._client("client-bsa", "BARBOSA SUPERMERCADOS")
        self.parent_type = PlanningInventoryType.objects.create(
            external_id="type-total",
            name="INVENTÁRIO OFICIAL ( TOTAL )",
            code="T",
            kind=PlanningInventoryType.Kind.PARENT,
            synced_at=self.now,
            last_seen_at=self.now,
        )

    def _region(self, external_id, name):
        return PlanningRegion.objects.create(
            external_id=external_id,
            name=name,
            state="SP",
            synced_at=self.now,
            last_seen_at=self.now,
        )

    def _client(self, external_id, trade_name):
        return PlanningClient.objects.create(
            external_id=external_id,
            trade_name=trade_name,
            synced_at=self.now,
            last_seen_at=self.now,
        )

    def _event(self, *, status="PLANNED", external_id="event-cpn"):
        store = PlanningStore.objects.create(
            external_id=f"store-{external_id}",
            client=self.external_oxxo,
            region=self.region,
            code="OXX17",
            store_number="17",
            name="OXXO 17",
            city="CAMPINAS",
            state="SP",
            synced_at=self.now,
            last_seen_at=self.now,
        )
        return PlanningEvent.objects.create(
            external_id=external_id,
            status=status,
            planned_at=timezone.make_aware(datetime(2026, 7, 16, 22, 0)),
            planned_pieces=260000,
            planned_headcount=12,
            store=store,
            client=self.external_oxxo,
            region=self.region,
            inventory_type=self.parent_type,
            synced_at=self.now,
            last_seen_at=self.now,
            sensitive_data_filtered=True,
        )

    def test_suggestions_are_operation_aware_and_do_not_persist(self):
        client_suggestion = suggest_local_clients(self.external_oxxo)
        base_suggestion = suggest_operational_bases(self.region, self.oxxo_client)
        regular_suggestion = suggest_operational_bases(self.region, self.regular_client)

        self.assertEqual(client_suggestion.best.instance, self.oxxo_client)
        self.assertEqual(base_suggestion.best.instance, self.oxxo_base)
        self.assertEqual(regular_suggestion.best.instance, self.regular_base)
        self.assertFalse(PlanningClientBinding.objects.exists())
        self.assertFalse(PlanningOperationalBaseBinding.objects.exists())

    def test_simple_region_binding_is_not_used_when_operation_is_ambiguous(self):
        PlanningRegionBinding.objects.create(
            planning_region=self.region,
            local_base=self.regular_base,
        )

        resolution = OperationalBaseResolver.resolve(
            planning_client=self.external_oxxo,
            planning_region=self.region,
            local_client=self.oxxo_client,
        )

        self.assertFalse(resolution.is_resolved)
        self.assertEqual(resolution.code, "operational_base_binding_missing")

    def test_combined_binding_has_priority_and_materialization_is_idempotent(self):
        PlanningClientBinding.objects.create(
            planning_client=self.external_oxxo,
            local_client=self.oxxo_client,
        )
        PlanningRegionBinding.objects.create(
            planning_region=self.region,
            local_base=self.regular_base,
        )
        PlanningOperationalBaseBinding.objects.create(
            planning_client=self.external_oxxo,
            planning_region=self.region,
            local_base=self.oxxo_base,
            reason="Operação OXX confirmada",
        )
        event = self._event()
        materializer = PlanningEventMaterializer()

        first = materializer.materialize(event)
        second = materializer.materialize(event)

        self.assertTrue(first[1])
        self.assertFalse(second[1])
        self.assertEqual(Inventario.objects.count(), 1)
        self.assertEqual(Inventario.objects.get().base, self.oxxo_base)

    def test_cancelled_unbound_event_is_skipped_without_local_inventory(self):
        event = self._event(status="CANCELLED", external_id="event-cancelled")

        PlanningEventMaterializer().materialize(event)

        event.refresh_from_db()
        self.assertEqual(event.materialization_status, PlanningEvent.MaterializationStatus.SKIPPED)
        self.assertEqual(event.materialization_error, "external_status_cancelled")
        self.assertFalse(Inventario.objects.exists())


class MappingPermissionAndRunTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("mapping-user", password="test-password")
        Perfil.objects.update_or_create(
            user=self.user,
            defaults={"role": Perfil.Role.OPERADOR},
        )
        self.client = HttpClient()
        self.client.force_login(self.user)

    def test_mapping_screen_requires_specific_permission(self):
        url = reverse("integracao:planning_mappings")
        self.assertEqual(self.client.get(url).status_code, 403)

        permission = Permission.objects.get(codename="gerenciar_mapeamentos_planning")
        self.user.user_permissions.add(permission)
        self.user = User.objects.get(pk=self.user.pk)
        self.client.force_login(self.user)

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mapeamentos Inventory Planning")

    def test_client_confirmation_is_permissioned_and_idempotent(self):
        permission = Permission.objects.get(codename="gerenciar_mapeamentos_planning")
        self.user.user_permissions.add(permission)
        self.user = User.objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        now = timezone.now()
        planning_client = PlanningClient.objects.create(
            external_id="client-safe",
            trade_name="CLIENTE SEGURO",
            synced_at=now,
            last_seen_at=now,
        )
        local_client = Cliente.objects.create(sigla="SEG", nome="CLIENTE SEGURO")
        payload = {
            "action": "confirm_client",
            "planning_client": planning_client.pk,
            "local_client": local_client.pk,
        }

        first = self.client.post(reverse("integracao:planning_mappings"), payload)
        second = self.client.post(reverse("integracao:planning_mappings"), payload)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(PlanningClientBinding.objects.count(), 1)

    def test_materialization_action_requires_separate_permission(self):
        permission = Permission.objects.get(codename="gerenciar_mapeamentos_planning")
        self.user.user_permissions.add(permission)
        self.user = User.objects.get(pk=self.user.pk)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("integracao:planning_mappings"),
            {"action": "materialize_resolved"},
        )

        self.assertEqual(response.status_code, 403)

    def test_interrupted_sync_closes_run(self):
        class InterruptedClient:
            def iter_pages(self, endpoint, *, params=None):
                raise KeyboardInterrupt
                yield  # pragma: no cover

        service = InventoryPlanningService(
            client=InterruptedClient(),
            repository=InventoryPlanningRepository(),
        )
        with self.assertRaises(KeyboardInterrupt):
            service.sync_catalog("regions")

        run = InventoryPlanningSyncRun.objects.get(endpoint="regions")
        self.assertEqual(run.status, InventoryPlanningSyncRun.Status.FAILED)
        self.assertEqual(run.error_code, "INTERRUPTED")
        self.assertIsNotNone(run.finished_at)

    def test_stale_command_only_marks_old_runs(self):
        old = InventoryPlanningSyncRun.objects.create(endpoint="events")
        recent = InventoryPlanningSyncRun.objects.create(endpoint="clients")
        InventoryPlanningSyncRun.objects.filter(pk=old.pk).update(
            started_at=timezone.now() - timedelta(hours=2),
        )
        output = StringIO()

        call_command("mark_stale_inventory_planning_runs", minutes=30, stdout=output)

        old.refresh_from_db()
        recent.refresh_from_db()
        self.assertEqual(old.status, InventoryPlanningSyncRun.Status.STALE)
        self.assertEqual(recent.status, InventoryPlanningSyncRun.Status.RUNNING)
        self.assertIn("1", output.getvalue())
