import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from insumos.models import Inventario
from integracao.models import (
    InventoryPlanningEventBinding,
    PlanningEvent,
    PlanningInventoryType,
    SyncState,
)
from integracao.exceptions import InventoryPlanningConfigurationError
from integracao.services.operational_base_resolver import (
    OperationalBaseResolver,
    PlanningClientResolver,
)


logger = logging.getLogger("integracao.inventory_planning")


class PlanningEventMaterializer:
    PLANNING_FIELDS = (
        "cliente",
        "loja",
        "base",
        "data_inicio",
        "inicio_previsto",
        "endereco",
        "bairro",
        "cidade",
        "cep",
        "cnpj",
        "dados_brutos",
        "tipo",
        "pessoas",
        "observacao",
        "ponto_encontro",
        "horario_inicio",
        "equipe_plan",
        "previsao_pecas",
    )
    FORECAST_FIELDS_AFTER_EXECUTION = (
        "inicio_previsto",
        "equipe_plan",
        "previsao_pecas",
    )
    SKIPPED_EXTERNAL_STATUSES = {"CANCELLED", "REMOVED"}

    @staticmethod
    def _system_user():
        User = get_user_model()
        username = settings.INVENTORY_PLANNING_SYSTEM_USERNAME
        user, created = User.objects.get_or_create(username=username)
        if not created and user.has_usable_password():
            raise InventoryPlanningConfigurationError(
                "INVENTORY_PLANNING_SYSTEM_USERNAME pertence a um usuário interativo."
            )
        if created:
            user.set_unusable_password()
            user.is_staff = False
            user.is_superuser = False
            user.save(update_fields=("password", "is_staff", "is_superuser"))
        return user

    def _planning_values(self, event, *, local_client, local_base):
        local_planned_at = timezone.localtime(event.planned_at)
        store = event.store
        import_data = event.import_data or {}
        return {
            "cliente": local_client,
            "loja": str(
                (store.store_number if store else "")
                or (store.code if store else "")
                or (store.name if store else "")
                or event.external_id
            )[:50],
            "base": local_base,
            "data_inicio": local_planned_at.date(),
            "inicio_previsto": event.planned_at,
            "endereco": (store.address if store else "") or import_data.get("endereco") or "",
            "bairro": (store.district if store else "") or import_data.get("bairro") or "",
            "cidade": (store.city if store else "") or import_data.get("cidade") or "",
            "cep": (store.zip_code if store else "") or import_data.get("cep") or "",
            "cnpj": store.corporate_document if store else "",
            "dados_brutos": import_data,
            "tipo": (event.inventory_type.code or event.inventory_type.name)[:20],
            "pessoas": event.planned_headcount,
            "observacao": event.notes,
            "ponto_encontro": event.meeting_point_name,
            "horario_inicio": local_planned_at.time().replace(tzinfo=None),
            "equipe_plan": event.planned_headcount,
            "previsao_pecas": event.planned_pieces,
        }

    def materialize(self, event):
        event = PlanningEvent.objects.select_related(
            "inventory_type",
            "store",
            "client",
            "region",
        ).get(pk=event.pk)

        if (
            event.inventory_type_id
            and event.inventory_type.kind == PlanningInventoryType.Kind.CHILD
        ):
            if not event.parent_external_id or not event.parent_id:
                return self._mark_error(event, "child_parent_missing")
            event.materialization_status = PlanningEvent.MaterializationStatus.NOT_APPLICABLE
            event.materialization_error = ""
            event.save(update_fields=("materialization_status", "materialization_error"))
            return None, False, "child"

        if not event.inventory_type_id or event.inventory_type.kind != PlanningInventoryType.Kind.PARENT:
            return self._mark_error(event, "inventory_type_invalid")
        if event.parent_external_id:
            return self._mark_error(event, "parent_event_has_parent")

        existing_binding = InventoryPlanningEventBinding.objects.filter(
            planning_event=event,
        ).select_related("inventory").first()
        if event.status in self.SKIPPED_EXTERNAL_STATUSES and existing_binding is None:
            event.materialization_status = PlanningEvent.MaterializationStatus.SKIPPED
            event.materialization_error = f"external_status_{event.status.lower()}"
            event.save(update_fields=("materialization_status", "materialization_error"))
            return None, False, "skipped"

        if not event.store_id:
            return self._mark_pending(event, "store_missing")
        if not event.client_id:
            return self._mark_pending(event, "client_missing")
        if not event.region_id:
            return self._mark_pending(event, "region_missing")

        client_resolution = PlanningClientResolver.resolve(event.client)
        if not client_resolution.binding:
            return self._mark_pending(event, "client_binding_missing")
        base_resolution = OperationalBaseResolver.resolve(
            planning_client=event.client,
            planning_region=event.region,
            local_client=client_resolution.local_client,
        )
        if not base_resolution.is_resolved:
            return self._mark_pending(event, base_resolution.code)

        values = self._planning_values(
            event,
            local_client=client_resolution.local_client,
            local_base=base_resolution.base,
        )
        with transaction.atomic():
            binding = InventoryPlanningEventBinding.objects.select_for_update().filter(
                planning_event=event
            ).select_related("inventory").first()
            created = binding is None
            if created:
                inventory = Inventario.objects.create(
                    **values,
                    status="PLANEJADO",
                    criado_por=self._system_user(),
                )
                InventoryPlanningEventBinding.objects.create(
                    planning_event=event,
                    inventory=inventory,
                )
            else:
                inventory = binding.inventory
                execution_started = bool(
                    inventory.status != "PLANEJADO"
                    or inventory.inicio_real
                    or inventory.fim_real
                    or inventory.inicio_contagem
                    or inventory.fim_contagem
                )
                update_fields = (
                    self.FORECAST_FIELDS_AFTER_EXECUTION
                    if execution_started
                    else self.PLANNING_FIELDS
                )
                for field in update_fields:
                    value = values[field]
                    setattr(inventory, field, value)
                inventory.save(update_fields=update_fields)
            event.materialization_status = PlanningEvent.MaterializationStatus.MATERIALIZED
            event.materialization_error = ""
            event.save(update_fields=("materialization_status", "materialization_error"))
        return inventory, created, "materialized"

    @staticmethod
    def _mark_pending(event, code):
        event.materialization_status = PlanningEvent.MaterializationStatus.PENDING
        event.materialization_error = code
        event.save(update_fields=("materialization_status", "materialization_error"))
        return None, False, code

    @staticmethod
    def _mark_error(event, code):
        event.materialization_status = PlanningEvent.MaterializationStatus.ERROR
        event.materialization_error = code
        event.save(update_fields=("materialization_status", "materialization_error"))
        return None, False, code

    @staticmethod
    def _has_resolved_bindings(event):
        if (
            not event.inventory_type_id
            or event.inventory_type.kind != PlanningInventoryType.Kind.PARENT
            or not event.store_id
            or not event.client_id
            or not event.region_id
        ):
            return False
        client_resolution = PlanningClientResolver.resolve(event.client)
        if not client_resolution.binding:
            return False
        return OperationalBaseResolver.resolve(
            planning_client=event.client,
            planning_region=event.region,
            local_client=client_resolution.local_client,
        ).is_resolved

    def materialize_all(self, *, resolved_only=False):
        materialized = 0
        pending = 0
        queryset = PlanningEvent.objects.filter(
            data_source="INVENTORY_PLANNING",
            sync_state=SyncState.PRESENT,
        ).select_related("inventory_type", "store", "client", "region")
        for event in queryset.iterator():
            if resolved_only and not self._has_resolved_bindings(event):
                continue
            try:
                _inventory, created, result = self.materialize(event)
            except Exception as exc:
                logger.error(
                    "inventory_planning_materialization_event_failed event_id=%s error_code=%s",
                    event.external_id,
                    exc.__class__.__name__,
                )
                fresh_event = PlanningEvent.objects.get(pk=event.pk)
                self._mark_error(fresh_event, "unexpected_materialization_error")
                pending += 1
                continue
            if result == "materialized":
                materialized += int(created)
            elif result not in {"child", "skipped"}:
                pending += 1
        return materialized, pending
