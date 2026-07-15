from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist

from estoque.models import Base
from integracao.models import (
    PlanningClientBinding,
    PlanningOperationalBaseBinding,
    PlanningRegionBinding,
)
from integracao.services.binding_suggestions import (
    operational_comparison_name,
    suggest_operational_bases,
)


@dataclass(frozen=True)
class ClientResolution:
    binding: PlanningClientBinding | None

    @property
    def local_client(self):
        return self.binding.local_client if self.binding else None


@dataclass(frozen=True)
class OperationalBaseResolution:
    base: Base | None
    code: str
    source: str = ""
    binding: object | None = None

    @property
    def is_resolved(self):
        return self.base is not None

    @property
    def is_ambiguous(self):
        return self.code == "operational_base_binding_ambiguous"


class PlanningClientResolver:
    @staticmethod
    def resolve(planning_client):
        if planning_client is None:
            return ClientResolution(None)
        try:
            binding = planning_client.local_binding
        except ObjectDoesNotExist:
            binding = None
        if binding is not None and not binding.is_active:
            binding = None
        return ClientResolution(binding)


class OperationalBaseResolver:
    @staticmethod
    def region_is_unambiguous(planning_region, *, bases=None):
        region_core = operational_comparison_name(planning_region.name)
        matching = []
        bases = bases if bases is not None else Base.objects.all().only("pk", "nome")
        for base in bases:
            base_core = operational_comparison_name(base.nome)
            if (
                base_core == region_core
                or base_core.startswith(region_core + " ")
                or region_core.startswith(base_core + " ")
                or base_core.endswith(" " + region_core)
            ):
                matching.append(base.pk)
        return len(set(matching)) == 1

    @classmethod
    def resolve(cls, *, planning_client, planning_region, local_client):
        if not planning_client or not planning_region or not local_client:
            return OperationalBaseResolution(
                None,
                "operational_base_binding_missing",
            )

        combined = PlanningOperationalBaseBinding.objects.filter(
            planning_client=planning_client,
            planning_region=planning_region,
            is_active=True,
        ).select_related("local_base").first()
        if combined:
            return OperationalBaseResolution(
                combined.local_base,
                "resolved",
                source="COMBINED",
                binding=combined,
            )

        simple = PlanningRegionBinding.objects.filter(
            planning_region=planning_region,
            is_active=True,
        ).select_related("local_base").first()
        if simple and cls.region_is_unambiguous(planning_region):
            suggestion = suggest_operational_bases(
                planning_region,
                local_client,
            )
            if (
                suggestion.best
                and not suggestion.ambiguous
                and suggestion.best.score >= 80
                and suggestion.best.instance.pk == simple.local_base_id
            ):
                return OperationalBaseResolution(
                    simple.local_base,
                    "resolved",
                    source="REGION_FALLBACK",
                    binding=simple,
                )

        suggestion = suggest_operational_bases(planning_region, local_client)
        if suggestion.ambiguous:
            return OperationalBaseResolution(
                None,
                "operational_base_binding_ambiguous",
            )
        return OperationalBaseResolution(
            None,
            "operational_base_binding_missing",
        )
