from copy import deepcopy
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth.models import User
from django.test import TestCase

from estoque.models import Base, Empresa
from insumos.models import Cliente, Inventario
from integracao.models import (
    InventoryPlanningEventBinding,
    InventoryPlanningSyncRun,
    PlanningClient,
    PlanningClientBinding,
    PlanningEvent,
    PlanningInventoryType,
    PlanningRegion,
    PlanningRegionBinding,
    PlanningStore,
    SyncState,
)
from integracao.repositories.planning_repository import InventoryPlanningRepository
from integracao.services.inventory_planning_service import (
    InventoryPlanningService,
    InventoryPlanningSyncAlreadyRunning,
)


class FakeClient:
    def __init__(self, pages=None):
        self.pages = pages or {}

    def iter_pages(self, endpoint, *, params=None):
        key = endpoint.strip("/")
        configured = self.pages.get(key, [[]])
        for number, items in enumerate(configured, start=1):
            yield items, {
                "page": number,
                "pageCount": len(configured),
                "perPage": 100,
                "total": sum(len(page) for page in configured),
            }, {}


class InventoryPlanningSyncTests(TestCase):
    def setUp(self):
        self.repository = InventoryPlanningRepository()
        self.empresa = Empresa.objects.create(nome="Inventory Brasil")
        self.base = Base.objects.create(nome="SP SUL", empresa=self.empresa)
        self.local_client = Cliente.objects.create(sigla="BSA", nome="Barbosa")
        self.region_payload = {"id": "region-sp-sul", "name": "SP SUL", "state": "SP"}
        self.client_payload = {
            "id": "client-bsa",
            "corporateName": "SILVA E BARBOSA COMERCIO LTDA",
            "tradeName": "BARBOSA SUPERMERCADOS",
        }
        self.store_payload = {
            "id": "store-bsa-25",
            "code": "BSA25",
            "storeNumber": "25",
            "name": "BSA",
            "city": "SÃO PAULO",
            "state": "SP",
            "zipCode": "05876040",
            "client": self.client_payload,
            "regional": self.region_payload,
        }
        self.parent_type = {
            "id": "type-total",
            "name": "INVENTÁRIO OFICIAL ( TOTAL )",
            "code": "T",
            "type": "PAI",
        }
        self.child_type = {
            "id": "type-folga",
            "name": "FOLGA",
            "code": "F",
            "type": "FILHO",
        }
        self.parent_event = {
            "id": "event-parent",
            "status": "PLANNED",
            "plannedAt": "2026-07-16T01:00:00.000Z",
            "plannedPieces": 260000,
            "notes": "NOTURNO",
            "parentEventId": None,
            "store": self.store_payload,
            "inventoryType": self.parent_type,
            "importData": {
                "endereco": "RUA EXEMPLO, 123",
                "bairro": "CENTRO",
                "pessoasPrevistas": 12,
                "horarioInicio": "22:00",
            },
            "metrics": [
                {"metric": "PLANNED_HEADCOUNT", "value": 12},
                {"metric": "PLANNED_PIECES", "value": 260000},
            ],
            "createdAt": "2026-07-01T10:00:00Z",
            "updatedAt": "2026-07-15T10:00:00Z",
        }
        self.child_event = {
            "id": "event-child",
            "status": "PLANNED",
            "plannedAt": "2026-07-15T14:00:00.000Z",
            "plannedPieces": None,
            "store": {
                "id": "store-bsa-25",
                "code": "BSA25",
                "storeNumber": "25",
                "name": "BSA",
                "city": "SÃO PAULO",
                "state": "SP",
            },
            "inventoryType": self.child_type,
            "importData": {"horarioInicio": "11:00"},
            "metrics": [],
        }
        self.parent_event["children"] = [self.child_event]

    def _create_bindings(self):
        planning_client = self.repository.upsert_client(self.client_payload)[0]
        planning_region = self.repository.upsert_region(self.region_payload)[0]
        PlanningClientBinding.objects.create(
            planning_client=planning_client,
            local_client=self.local_client,
        )
        PlanningRegionBinding.objects.create(
            planning_region=planning_region,
            local_base=self.base,
        )

    def _sync_events(self, items, *, materialize=True):
        service = InventoryPlanningService(
            client=FakeClient({"events": [items]}),
            repository=self.repository,
        )
        return service.sync_events(materialize=materialize)

    def test_parent_child_and_idempotent_materialization(self):
        self._create_bindings()

        first = self._sync_events([self.parent_event])
        second = self._sync_events([self.parent_event])

        self.assertEqual(PlanningEvent.objects.count(), 2)
        self.assertEqual(Inventario.objects.count(), 1)
        self.assertEqual(InventoryPlanningEventBinding.objects.count(), 1)
        parent = PlanningEvent.objects.get(external_id="event-parent")
        child = PlanningEvent.objects.get(external_id="event-child")
        inventory = parent.inventory_binding.inventory
        self.assertEqual(child.parent, parent)
        self.assertEqual(child.materialization_status, PlanningEvent.MaterializationStatus.NOT_APPLICABLE)
        self.assertEqual(inventory.loja, "25")
        self.assertEqual(inventory.tipo, "T")
        self.assertEqual(inventory.pessoas, 12)
        self.assertEqual(inventory.previsao_pecas, 260000)
        self.assertEqual(inventory.horario_inicio.hour, 22)
        self.assertEqual(first.created, 2)
        self.assertEqual(second.created, 0)

    def test_event_without_explicit_bindings_remains_pending(self):
        run = self._sync_events([self.parent_event])

        event = PlanningEvent.objects.get(external_id="event-parent")
        self.assertEqual(event.materialization_status, PlanningEvent.MaterializationStatus.PENDING)
        self.assertEqual(event.materialization_error, "client_binding_missing")
        self.assertEqual(run.pending_materialization, 1)
        self.assertFalse(Inventario.objects.exists())

    def test_modified_and_cancelled_event_preserves_local_execution(self):
        self._create_bindings()
        self._sync_events([self.parent_event])
        inventory = Inventario.objects.get()
        inventory.total_pecas = 255000
        inventory.inicio_real = datetime(2026, 7, 16, 1, 12, tzinfo=dt_timezone.utc)
        inventory.status = "EM_ANDAMENTO"
        inventory.save()

        modified = deepcopy(self.parent_event)
        modified["status"] = "MODIFIED"
        modified["plannedPieces"] = 270000
        modified["metrics"][1]["value"] = 270000
        modified["updatedAt"] = "2026-07-15T12:00:00Z"
        self._sync_events([modified])

        inventory.refresh_from_db()
        event = PlanningEvent.objects.get(external_id="event-parent")
        self.assertEqual(event.status, "MODIFIED")
        self.assertEqual(inventory.previsao_pecas, 270000)
        self.assertEqual(inventory.total_pecas, 255000)
        self.assertIsNotNone(inventory.inicio_real)
        self.assertEqual(inventory.status, "EM_ANDAMENTO")

        cancelled = deepcopy(modified)
        cancelled["status"] = "CANCELLED"
        cancelled["updatedAt"] = "2026-07-15T13:00:00Z"
        self._sync_events([cancelled])
        self.assertEqual(PlanningEvent.objects.get(external_id="event-parent").status, "CANCELLED")
        self.assertTrue(Inventario.objects.filter(pk=inventory.pk).exists())

    def test_older_external_update_does_not_regress_event(self):
        self._sync_events([self.parent_event], materialize=False)
        older = deepcopy(self.parent_event)
        older["plannedPieces"] = 1
        older["updatedAt"] = "2026-07-14T10:00:00Z"

        self._sync_events([older], materialize=False)

        event = PlanningEvent.objects.get(external_id="event-parent")
        self.assertEqual(event.planned_pieces, 260000)
        self.assertEqual(event.external_updated_at.isoformat(), "2026-07-15T10:00:00+00:00")

    def test_missing_event_is_tombstoned_only_after_complete_snapshot(self):
        extra = deepcopy(self.parent_event)
        extra["id"] = "event-extra"
        extra["children"] = []
        self._sync_events([self.parent_event, extra], materialize=False)

        self._sync_events([self.parent_event], materialize=False)

        self.assertEqual(
            PlanningEvent.objects.get(external_id="event-extra").sync_state,
            SyncState.MISSING,
        )
        self.assertTrue(PlanningEvent.objects.filter(external_id="event-extra").exists())

    def test_optional_fields_and_sensitive_import_data(self):
        payload = deepcopy(self.parent_event)
        payload["id"] = "event-minimal"
        payload["notes"] = None
        payload["plannedPieces"] = None
        payload["metrics"] = []
        payload["children"] = []
        payload["importData"] = {
            "cidade": "SÃO PAULO",
            "documentCpf": "12345678901",
            "bankAccounts": [{"pixKey": "12345678901"}],
        }

        self._sync_events([payload], materialize=False)

        event = PlanningEvent.objects.get(external_id="event-minimal")
        self.assertIsNone(event.planned_pieces)
        self.assertIsNone(event.planned_headcount)
        self.assertEqual(event.notes, "")
        self.assertEqual(event.import_data, {"cidade": "SÃO PAULO"})
        self.assertTrue(event.sensitive_data_filtered)

    def test_store_keeps_client_and_region_when_child_has_summary_only(self):
        self._sync_events([self.parent_event], materialize=False)

        store = PlanningStore.objects.get(external_id="store-bsa-25")
        self.assertEqual(store.client.external_id, "client-bsa")
        self.assertEqual(store.region.external_id, "region-sp-sul")
        self.assertEqual(store.city, "SÃO PAULO")

    def test_catalog_sync_is_paginated_and_idempotent(self):
        client = FakeClient({"regions": [[self.region_payload], [self.region_payload]]})
        service = InventoryPlanningService(client=client, repository=self.repository)

        first = service.sync_catalog("regions")
        second = service.sync_catalog("regions")

        self.assertEqual(PlanningRegion.objects.count(), 1)
        self.assertEqual(first.pages, 2)
        self.assertEqual(first.received, 1)
        self.assertEqual(second.created, 0)
        self.assertEqual(InventoryPlanningSyncRun.objects.filter(status="SUCCESS").count(), 2)

    def test_rate_limit_headers_are_recorded(self):
        class RateLimitClient(FakeClient):
            def iter_pages(self, endpoint, *, params=None):
                yield [self.pages["regions"][0][0]], {
                    "page": 1,
                    "pageCount": 1,
                    "perPage": 100,
                    "total": 1,
                }, {
                    "RateLimit-Limit": "1000",
                    "RateLimit-Remaining": "987",
                    "RateLimit-Reset": "120",
                }

        run = InventoryPlanningService(
            client=RateLimitClient({"regions": [[self.region_payload]]}),
            repository=self.repository,
        ).sync_catalog("regions")

        self.assertEqual(run.rate_limit_limit, 1000)
        self.assertEqual(run.rate_limit_remaining, 987)
        self.assertEqual(run.rate_limit_reset, 120)

    def test_overlapping_sync_for_same_endpoint_is_rejected(self):
        InventoryPlanningSyncRun.objects.create(endpoint="events", status="RUNNING")
        service = InventoryPlanningService(
            client=FakeClient({"events": [[self.parent_event]]}),
            repository=self.repository,
        )

        with self.assertRaises(InventoryPlanningSyncAlreadyRunning):
            service.sync_events(materialize=False)

    def test_same_type_name_can_exist_as_parent_and_child(self):
        parent_type = deepcopy(self.parent_type)
        parent_type.update(id="project-parent", name="PROJETO FIXO", code="PF")
        child_type = deepcopy(self.child_type)
        child_type.update(id="project-child", name="PROJETO FIXO", code="PF-AUX")

        self.repository.upsert_inventory_type(parent_type)
        self.repository.upsert_inventory_type(child_type)

        self.assertEqual(
            PlanningInventoryType.objects.get(external_id="project-parent").kind,
            "PAI",
        )
        self.assertEqual(
            PlanningInventoryType.objects.get(external_id="project-child").kind,
            "FILHO",
        )

    def test_child_without_parent_is_isolated_as_inconsistent(self):
        child = deepcopy(self.child_event)
        child["parentEventId"] = None

        self._sync_events([child])

        event = PlanningEvent.objects.get(external_id="event-child")
        self.assertEqual(event.materialization_status, PlanningEvent.MaterializationStatus.ERROR)
        self.assertEqual(event.materialization_error, "child_parent_missing")
        self.assertFalse(Inventario.objects.exists())
