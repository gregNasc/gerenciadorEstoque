from django.core.management.base import BaseCommand

from integracao.models import (
    PlanningClientBinding,
    PlanningEvent,
    PlanningOperationalBaseBinding,
    PlanningRegionBinding,
)


class Command(BaseCommand):
    help = "Lista bindings confirmados e contagens de pendências do planejamento."

    def handle(self, *args, **options):
        self.stdout.write("CLIENTES")
        for binding in PlanningClientBinding.objects.select_related(
            "planning_client", "local_client"
        ).order_by("planning_client__trade_name"):
            state = "ATIVO" if binding.is_active else "INATIVO"
            self.stdout.write(
                f"{binding.planning_client.external_id} | {binding.planning_client} | "
                f"{binding.local_client.sigla} | {state} | {binding.source}"
            )

        self.stdout.write("\nBASES COMBINADAS")
        for binding in PlanningOperationalBaseBinding.objects.select_related(
            "planning_client", "planning_region", "local_base"
        ).order_by("planning_client__trade_name", "planning_region__name"):
            state = "ATIVO" if binding.is_active else "INATIVO"
            self.stdout.write(
                f"{binding.planning_client} | {binding.planning_region.name} | "
                f"{binding.local_base.nome} | {state} | {binding.source}"
            )

        self.stdout.write("\nREGIONAIS FALLBACK")
        for binding in PlanningRegionBinding.objects.select_related(
            "planning_region", "local_base"
        ).order_by("planning_region__name"):
            state = "ATIVO" if binding.is_active else "INATIVO"
            self.stdout.write(
                f"{binding.planning_region.name} | {binding.local_base.nome} | "
                f"{state} | {binding.source}"
            )

        self.stdout.write("\nPENDÊNCIAS")
        errors = {}
        for code in PlanningEvent.objects.filter(
            materialization_status=PlanningEvent.MaterializationStatus.PENDING,
        ).values_list("materialization_error", flat=True):
            errors[code or "sem_codigo"] = errors.get(code or "sem_codigo", 0) + 1
        for code, count in sorted(errors.items()):
            self.stdout.write(f"{code}: {count}")
