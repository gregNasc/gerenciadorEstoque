from django.core.management.base import BaseCommand

from integracao.models import PlanningClient, PlanningEvent
from integracao.services.binding_suggestions import (
    suggest_local_clients,
    suggest_operational_bases,
)
from integracao.services.operational_base_resolver import PlanningClientResolver


class Command(BaseCommand):
    help = "Calcula sugestões de bindings sem criar ou alterar vínculos."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        limit = max(options["limit"], 1)
        self.stdout.write("SUGESTÕES DE CLIENTES (somente leitura)")
        clients = PlanningClient.objects.filter(
            events__materialization_status="PENDING",
        ).distinct().order_by("trade_name", "corporate_name")[:limit]
        for planning_client in clients:
            if PlanningClientResolver.resolve(planning_client).binding:
                continue
            suggestion = suggest_local_clients(planning_client)
            best = suggestion.best
            if best:
                self.stdout.write(
                    f"{planning_client.external_id} | {planning_client} | "
                    f"{best.instance.sigla} | {best.confidence} | {best.score} | {best.reason}"
                )
            else:
                self.stdout.write(f"{planning_client.external_id} | {planning_client} | SEM CANDIDATO")

        self.stdout.write("\nSUGESTÕES DE BASES (somente leitura)")
        pairs = PlanningEvent.objects.filter(
            materialization_status="PENDING",
            client__isnull=False,
            region__isnull=False,
        ).values_list("client_id", "region_id").distinct()[:limit]
        for client_id, region_id in pairs:
            event = PlanningEvent.objects.select_related("client", "region").filter(
                client_id=client_id,
                region_id=region_id,
            ).first()
            resolution = PlanningClientResolver.resolve(event.client)
            if not resolution.local_client:
                continue
            suggestion = suggest_operational_bases(event.region, resolution.local_client)
            best = suggestion.best
            if best:
                ambiguity = "AMBÍGUO" if suggestion.ambiguous else best.confidence
                self.stdout.write(
                    f"{event.client} | {event.region.name} | {best.instance.nome} | "
                    f"{ambiguity} | {best.score} | {best.reason}"
                )
            else:
                self.stdout.write(f"{event.client} | {event.region.name} | SEM CANDIDATO")
