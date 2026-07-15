from datetime import datetime, time, timedelta

from django.utils import timezone

from integracao.models import PlanningEvent, PlanningInventoryType, SyncState


class PlanningService:
    """Porta de leitura do domínio para planejamento externo sincronizado."""

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
