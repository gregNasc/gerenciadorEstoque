from django.core.management.base import BaseCommand, CommandError

from integracao.clients.inventory_planning import InventoryPlanningClient
from integracao.exceptions import InventoryPlanningError
from integracao.sync.orchestrator import InventoryPlanningSyncOrchestrator


class Command(BaseCommand):
    help = "Sincroniza catálogos e eventos da Inventory Planning API."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--catalogs-only", action="store_true")
        group.add_argument("--events-only", action="store_true")
        parser.add_argument(
            "--no-materialize",
            action="store_true",
            help="Sincroniza eventos sem criar/atualizar Inventario local.",
        )

    def handle(self, *args, **options):
        try:
            with InventoryPlanningClient() as client:
                service = InventoryPlanningSyncOrchestrator(client=client)
                if options["catalogs_only"]:
                    runs = [service.sync_catalog(endpoint) for endpoint in service.CATALOG_ENDPOINTS]
                elif options["events_only"]:
                    runs = [
                        service.sync_events(materialize=not options["no_materialize"])
                    ]
                else:
                    runs = service.sync_all(materialize=not options["no_materialize"])
        except InventoryPlanningError as exc:
            raise CommandError(str(exc)) from exc

        for run in runs:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{run.endpoint}: recebidos={run.received}, criados={run.created}, "
                    f"atualizados={run.updated}, ausentes={run.missing}, "
                    f"materializados={run.materialized}, pendentes={run.pending_materialization}"
                )
            )
