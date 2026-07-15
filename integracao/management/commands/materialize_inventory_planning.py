from django.core.management.base import BaseCommand

from integracao.services.materialization import PlanningEventMaterializer


class Command(BaseCommand):
    help = "Materializa eventos PAI já sincronizados após configurar os bindings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--resolved-only",
            action="store_true",
            help="Processa somente eventos cujos bindings já resolvem cliente e base.",
        )

    def handle(self, *args, **options):
        materialized, pending = PlanningEventMaterializer().materialize_all(
            resolved_only=options["resolved_only"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Inventários criados={materialized}; eventos pendentes={pending}."
            )
        )
