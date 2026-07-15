from datetime import datetime, time, timedelta

from django.db.models import Max, Q
from django.utils import timezone

from integracao.models import (
    InventoryPlanningEventBinding,
    InventoryPlanningSyncRun,
    PlanningClientBinding,
    PlanningEvent,
    PlanningInventoryType,
    PlanningOperationalBaseBinding,
    PlanningRegionBinding,
    SyncState,
)
from integracao.services.operational_base_resolver import OperationalBaseResolver
from integracao.services.binding_suggestions import suggest_operational_bases


class PlanningService:
    """Porta de leitura do domínio para planejamento externo sincronizado."""

    ACTIVE_EVENT_STATUSES = (
        "PRE_PLANNED",
        "PLANNED",
        "APPROVED",
        "IN_PROGRESS",
        "ADDED",
        "MODIFIED",
    )

    @staticmethod
    def events(*, start=None, end=None, region=None, status=None, parents_only=False):
        queryset = PlanningEvent.objects.filter(
            sync_state=SyncState.PRESENT,
        ).select_related("store", "client", "region", "inventory_type", "parent")
        if start:
            queryset = queryset.filter(planned_at__gte=start)
        if end:
            queryset = queryset.filter(planned_at__lte=end)
        if region:
            queryset = queryset.filter(region=region)
        if status:
            queryset = queryset.filter(status__in=status)
        if parents_only:
            queryset = queryset.filter(
                inventory_type__kind=PlanningInventoryType.Kind.PARENT,
                parent_external_id="",
            )
        return queryset.order_by("planned_at", "external_id")

    @classmethod
    def events_for_day(cls, day=None, **filters):
        day = day or timezone.localdate()
        start = timezone.make_aware(datetime.combine(day, time.min))
        end = start + timedelta(days=1)
        return cls.events(start=start, end=end, **filters)

    @staticmethod
    def _can_view_all_planning(user):
        perfil = getattr(user, "perfil", None)
        return bool(
            perfil
            and (
                perfil.is_admin
                or perfil.is_planejamento_insumos
                or perfil.is_executivo_insumos
            )
        )

    @staticmethod
    def _scope_for_local_bases(local_base_ids):
        local_base_ids = list(local_base_ids)
        visible_combined = list(
            PlanningOperationalBaseBinding.objects.filter(
                local_base_id__in=local_base_ids,
                is_active=True,
            ).values_list("planning_client_id", "planning_region_id")
        )
        simple_bindings = list(
            PlanningRegionBinding.objects.filter(
                local_base_id__in=local_base_ids,
                is_active=True,
            ).select_related("planning_region")
        )
        all_combined = set(
            PlanningOperationalBaseBinding.objects.filter(
                is_active=True,
            ).values_list("planning_client_id", "planning_region_id")
        )
        from estoque.models import Base

        all_bases = list(Base.objects.all().only("pk", "nome"))

        scope = Q(pk__in=[])
        for client_id, region_id in visible_combined:
            scope |= Q(client_id=client_id, region_id=region_id)
        client_bindings = PlanningClientBinding.objects.filter(
            is_active=True,
        ).select_related("planning_client", "local_client")
        for region_binding in simple_bindings:
            if not OperationalBaseResolver.region_is_unambiguous(
                region_binding.planning_region,
                bases=all_bases,
            ):
                continue
            for client_binding in client_bindings:
                pair = (
                    client_binding.planning_client_id,
                    region_binding.planning_region_id,
                )
                if pair in all_combined:
                    continue
                suggestion = suggest_operational_bases(
                    region_binding.planning_region,
                    client_binding.local_client,
                    queryset=all_bases,
                )
                if (
                    suggestion.best
                    and not suggestion.ambiguous
                    and suggestion.best.score >= 80
                    and suggestion.best.instance.pk == region_binding.local_base_id
                ):
                    scope |= Q(
                        client_id=client_binding.planning_client_id,
                        region_id=region_binding.planning_region_id,
                    )
        return scope

    @classmethod
    def events_for_user(
        cls,
        user,
        *,
        start=None,
        end=None,
        statuses=None,
        parents_only=False,
        external_event_id="",
        external_region_id="",
        external_client_id="",
        external_store_id="",
        inventory_type_kind="",
        inventory_type_name="",
        location="",
        local_base=None,
        local_client=None,
        store_lookup="",
    ):
        """Retorna somente planejamento que o usuário já pode ver no domínio local."""
        perfil = getattr(user, "perfil", None)
        if not perfil:
            return PlanningEvent.objects.none()

        queryset = PlanningEvent.objects.filter(
            sync_state=SyncState.PRESENT,
        ).select_related(
            "store",
            "client",
            "region",
            "inventory_type",
            "parent",
        ).prefetch_related("children")

        if not cls._can_view_all_planning(user):
            queryset = queryset.filter(
                cls._scope_for_local_bases(
                    perfil.regionais.values_list("pk", flat=True),
                )
            )

        if local_base is not None:
            queryset = queryset.filter(cls._scope_for_local_bases([local_base.pk]))
        if local_client is not None:
            bound_client_ids = PlanningClientBinding.objects.filter(
                local_client=local_client,
                is_active=True,
            ).values_list("planning_client_id", flat=True)
            queryset = queryset.filter(client_id__in=bound_client_ids)
        if start:
            queryset = queryset.filter(planned_at__gte=start)
        if end:
            queryset = queryset.filter(planned_at__lt=end)
        if statuses:
            queryset = queryset.filter(status__in=statuses)
        if parents_only:
            queryset = queryset.filter(
                inventory_type__kind=PlanningInventoryType.Kind.PARENT,
                parent_external_id="",
            )
        if external_event_id:
            queryset = queryset.filter(external_id=external_event_id)
        if external_region_id:
            queryset = queryset.filter(region__external_id=external_region_id)
        if external_client_id:
            queryset = queryset.filter(client__external_id=external_client_id)
        if external_store_id:
            queryset = queryset.filter(store__external_id=external_store_id)
        if inventory_type_kind:
            queryset = queryset.filter(inventory_type__kind=inventory_type_kind)
        if inventory_type_name:
            queryset = queryset.filter(inventory_type__name__icontains=inventory_type_name)
        if location:
            queryset = queryset.filter(
                Q(region__name__icontains=location)
                | Q(region__state__iexact=location)
                | Q(store__city__icontains=location)
                | Q(store__state__iexact=location)
                | Q(store__name__icontains=location)
                | Q(store__nickname__icontains=location)
                | Q(store__code__icontains=location)
            )
        if store_lookup:
            queryset = queryset.filter(
                Q(store__code__iexact=store_lookup)
                | Q(store__store_number__iexact=store_lookup)
                | Q(store__name__iexact=store_lookup)
                | Q(store__nickname__iexact=store_lookup)
            )
        return queryset.order_by("planned_at", "external_id")

    @staticmethod
    def local_execution_for_event(user, event):
        """Resolve a execução local apenas por vínculo explícito e respeitando o escopo."""
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        inventory_id = InventoryPlanningEventBinding.objects.filter(
            planning_event=event,
        ).values_list("inventory_id", flat=True).first()
        if not inventory_id:
            return None
        return secure_queryset_insumos(
            Inventario.objects.select_related("base", "cliente"),
            user,
            campo_base="base",
        ).filter(pk=inventory_id).first()

    @staticmethod
    def sync_health():
        latest_run = InventoryPlanningSyncRun.objects.filter(
            endpoint="events",
        ).order_by("-started_at").first()
        latest_data = PlanningEvent.objects.filter(
            sync_state=SyncState.PRESENT,
        ).aggregate(value=Max("synced_at"))["value"]
        return {
            "has_data": latest_data is not None,
            "synced_at": latest_data,
            "last_run_failed": bool(
                latest_run
                and latest_run.status == InventoryPlanningSyncRun.Status.FAILED
            ),
            "last_run_at": latest_run.started_at if latest_run else None,
        }
