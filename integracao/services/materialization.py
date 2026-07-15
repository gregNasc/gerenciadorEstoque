from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
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

    @staticmethod
    def _get_related_binding(instance):
        try:
            return instance.local_binding
        except ObjectDoesNotExist:
            return None

    def _planning_values(self, event):
        local_planned_at = timezone.localtime(event.planned_at)
        store = event.store
        import_data = event.import_data or {}
        client_binding = self._get_related_binding(event.client)
        region_binding = self._get_related_binding(event.region)
        return {
            "cliente": client_binding.local_client,
            "loja": str(
                (store.store_number if store else "")
                or (store.code if store else "")
                or (store.name if store else "")
                or event.external_id
            )[:50],
            "base": region_binding.local_base,
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
            "client__local_binding__local_client",
            "region__local_binding__local_base",
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
        if not event.store_id or not event.client_id or not event.region_id:
            return self._mark_pending(event, "catalog_binding_incomplete")
        if not self._get_related_binding(event.client):
            return self._mark_pending(event, "client_binding_missing")
        if not self._get_related_binding(event.region):
            return self._mark_pending(event, "region_binding_missing")

        values = self._planning_values(event)
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
                for field, value in values.items():
                    setattr(inventory, field, value)
                inventory.save(update_fields=self.PLANNING_FIELDS)
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

    def materialize_all(self):
        materialized = 0
        pending = 0
        queryset = PlanningEvent.objects.filter(
            data_source="INVENTORY_PLANNING",
            sync_state=SyncState.PRESENT,
        ).select_related("inventory_type")
        for event in queryset.iterator():
            _inventory, created, result = self.materialize(event)
            if result == "materialized":
                materialized += int(created)
            elif result not in {"child"}:
                pending += 1
        return materialized, pending
