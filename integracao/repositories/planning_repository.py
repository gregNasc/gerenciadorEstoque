from django.db import transaction
from django.utils import timezone

from integracao.constants import DATA_SOURCE_INVENTORY_PLANNING
from integracao.mappers.catalogs import (
    map_client,
    map_inventory_type,
    map_region,
    map_store,
)
from integracao.mappers.events import map_event
from integracao.models import (
    PlanningClient,
    PlanningEvent,
    PlanningInventoryType,
    PlanningRegion,
    PlanningStore,
    SyncState,
)


class InventoryPlanningRepository:
    CATALOG_MODELS = {
        "regions": PlanningRegion,
        "clients": PlanningClient,
        "stores": PlanningStore,
        "inventory-types": PlanningInventoryType,
    }

    @staticmethod
    def _sync_defaults(mapped, now):
        return {
            **mapped,
            "synced_at": now,
            "last_seen_at": now,
            "sync_state": SyncState.PRESENT,
        }

    @staticmethod
    def _is_stale(existing, external_updated_at):
        return bool(
            existing
            and existing.external_updated_at
            and external_updated_at
            and external_updated_at < existing.external_updated_at
        )

    @staticmethod
    def _result(instance, created, changed=True):
        return instance, created, bool(not created and changed)

    @staticmethod
    def _preserve_partial(existing, mapped, partial):
        if not existing or not partial:
            return mapped
        for key, value in tuple(mapped.items()):
            if value in (None, "", [], {}):
                mapped[key] = getattr(existing, key)
        return mapped

    def upsert_region(self, payload, *, now=None, partial=False):
        now = now or timezone.now()
        mapped = map_region(payload)
        external_id = mapped.pop("external_id")
        existing = PlanningRegion.objects.filter(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            external_id=external_id,
        ).first()
        mapped = self._preserve_partial(existing, mapped, partial)
        if self._is_stale(existing, mapped.get("external_updated_at")):
            PlanningRegion.objects.filter(pk=existing.pk).update(
                synced_at=now,
                last_seen_at=now,
                sync_state=SyncState.PRESENT,
            )
            existing.refresh_from_db()
            return self._result(existing, False, False)
        changed = not existing or any(getattr(existing, key) != value for key, value in mapped.items())
        instance, created = PlanningRegion.objects.update_or_create(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            external_id=external_id,
            defaults=self._sync_defaults(mapped, now),
        )
        return self._result(instance, created, changed)

    def upsert_client(self, payload, *, now=None, partial=False):
        now = now or timezone.now()
        mapped = map_client(payload)
        external_id = mapped.pop("external_id")
        existing = PlanningClient.objects.filter(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            external_id=external_id,
        ).first()
        mapped = self._preserve_partial(existing, mapped, partial)
        if self._is_stale(existing, mapped.get("external_updated_at")):
            PlanningClient.objects.filter(pk=existing.pk).update(
                synced_at=now,
                last_seen_at=now,
                sync_state=SyncState.PRESENT,
            )
            existing.refresh_from_db()
            return self._result(existing, False, False)
        changed = not existing or any(getattr(existing, key) != value for key, value in mapped.items())
        instance, created = PlanningClient.objects.update_or_create(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            external_id=external_id,
            defaults=self._sync_defaults(mapped, now),
        )
        return self._result(instance, created, changed)

    def upsert_inventory_type(self, payload, *, now=None, partial=False):
        now = now or timezone.now()
        mapped = map_inventory_type(payload)
        external_id = mapped.pop("external_id")
        existing = PlanningInventoryType.objects.filter(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            external_id=external_id,
        ).first()
        mapped = self._preserve_partial(existing, mapped, partial)
        if self._is_stale(existing, mapped.get("external_updated_at")):
            PlanningInventoryType.objects.filter(pk=existing.pk).update(
                synced_at=now,
                last_seen_at=now,
                sync_state=SyncState.PRESENT,
            )
            existing.refresh_from_db()
            return self._result(existing, False, False)
        changed = not existing or any(getattr(existing, key) != value for key, value in mapped.items())
        instance, created = PlanningInventoryType.objects.update_or_create(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            external_id=external_id,
            defaults=self._sync_defaults(mapped, now),
        )
        return self._result(instance, created, changed)

    def upsert_store(self, payload, *, now=None, partial=False):
        now = now or timezone.now()
        nested_client = payload.get("client")
        nested_region = payload.get("regional") or payload.get("region")
        client = (
            self.upsert_client(nested_client, now=now, partial=True)[0]
            if isinstance(nested_client, dict)
            else None
        )
        region = (
            self.upsert_region(nested_region, now=now, partial=True)[0]
            if isinstance(nested_region, dict)
            else None
        )
        mapped = map_store(payload)
        external_id = mapped.pop("external_id")
        client_external_id = mapped.pop("client_external_id")
        region_external_id = mapped.pop("region_external_id")
        if client is None and client_external_id:
            client = PlanningClient.objects.filter(
                data_source=DATA_SOURCE_INVENTORY_PLANNING,
                external_id=client_external_id,
            ).first()
        if region is None and region_external_id:
            region = PlanningRegion.objects.filter(
                data_source=DATA_SOURCE_INVENTORY_PLANNING,
                external_id=region_external_id,
            ).first()
        mapped.update(client=client, region=region)
        existing = PlanningStore.objects.filter(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            external_id=external_id,
        ).first()
        if existing and partial:
            client = client or existing.client
            region = region or existing.region
            mapped.update(client=client, region=region)
        mapped = self._preserve_partial(existing, mapped, partial)
        if self._is_stale(existing, mapped.get("external_updated_at")):
            PlanningStore.objects.filter(pk=existing.pk).update(
                synced_at=now,
                last_seen_at=now,
                sync_state=SyncState.PRESENT,
            )
            existing.refresh_from_db()
            return self._result(existing, False, False)
        changed = not existing or any(getattr(existing, key) != value for key, value in mapped.items())
        instance, created = PlanningStore.objects.update_or_create(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            external_id=external_id,
            defaults=self._sync_defaults(mapped, now),
        )
        return self._result(instance, created, changed)

    def upsert_catalog(self, endpoint, payload, *, now=None):
        handlers = {
            "regions": self.upsert_region,
            "clients": self.upsert_client,
            "stores": self.upsert_store,
            "inventory-types": self.upsert_inventory_type,
        }
        return handlers[endpoint](payload, now=now)

    @transaction.atomic
    def upsert_event(self, payload, *, now=None):
        now = now or timezone.now()
        mapped = map_event(payload)
        external_id = mapped.pop("external_id")
        nested_store = mapped.pop("nested_store")
        nested_type = mapped.pop("nested_type")

        store = self.upsert_store(nested_store, now=now, partial=True)[0] if nested_store else None
        inventory_type = (
            self.upsert_inventory_type(nested_type, now=now, partial=True)[0]
            if nested_type
            else None
        )
        if store is None and mapped["store_external_id"]:
            store = PlanningStore.objects.filter(
                data_source=DATA_SOURCE_INVENTORY_PLANNING,
                external_id=mapped["store_external_id"],
            ).first()
        if inventory_type is None and mapped["inventory_type_external_id"]:
            inventory_type = PlanningInventoryType.objects.filter(
                data_source=DATA_SOURCE_INVENTORY_PLANNING,
                external_id=mapped["inventory_type_external_id"],
            ).first()
        client = store.client if store else None
        region = store.region if store else None
        if client is None and mapped["client_external_id"]:
            client = PlanningClient.objects.filter(
                data_source=DATA_SOURCE_INVENTORY_PLANNING,
                external_id=mapped["client_external_id"],
            ).first()
        if region is None and mapped["region_external_id"]:
            region = PlanningRegion.objects.filter(
                data_source=DATA_SOURCE_INVENTORY_PLANNING,
                external_id=mapped["region_external_id"],
            ).first()

        for transient_key in (
            "store_external_id",
            "client_external_id",
            "region_external_id",
            "inventory_type_external_id",
        ):
            mapped.pop(transient_key)
        mapped.update(
            store=store,
            client=client,
            region=region,
            inventory_type=inventory_type,
        )
        existing = PlanningEvent.objects.filter(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            external_id=external_id,
        ).first()
        if self._is_stale(existing, mapped.get("external_updated_at")):
            PlanningEvent.objects.filter(pk=existing.pk).update(
                synced_at=now,
                last_seen_at=now,
                sync_state=SyncState.PRESENT,
            )
            existing.refresh_from_db()
            return self._result(existing, False, False)
        changed = not existing or existing.source_payload_hash != mapped["source_payload_hash"]
        if existing:
            mapped["materialization_status"] = existing.materialization_status
            mapped["materialization_error"] = existing.materialization_error
        instance, created = PlanningEvent.objects.update_or_create(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            external_id=external_id,
            defaults=self._sync_defaults(mapped, now),
        )
        return self._result(instance, created, changed)

    def resolve_event_parents(self):
        events = PlanningEvent.objects.filter(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
        ).exclude(parent_external_id="")
        parents = {
            item.external_id: item.pk
            for item in PlanningEvent.objects.filter(
                data_source=DATA_SOURCE_INVENTORY_PLANNING,
                external_id__in=events.values_list("parent_external_id", flat=True),
            )
        }
        changed = 0
        for event in events.only("pk", "parent_id", "parent_external_id"):
            parent_id = parents.get(event.parent_external_id)
            if event.parent_id != parent_id:
                PlanningEvent.objects.filter(pk=event.pk).update(parent_id=parent_id)
                changed += 1
        return changed

    def mark_missing(self, endpoint, seen_external_ids, *, now=None):
        now = now or timezone.now()
        model = self.CATALOG_MODELS.get(endpoint)
        if endpoint == "events":
            model = PlanningEvent
        queryset = model.objects.filter(
            data_source=DATA_SOURCE_INVENTORY_PLANNING,
            sync_state=SyncState.PRESENT,
        )
        if seen_external_ids:
            queryset = queryset.exclude(external_id__in=seen_external_ids)
        return queryset.update(sync_state=SyncState.MISSING, synced_at=now)
