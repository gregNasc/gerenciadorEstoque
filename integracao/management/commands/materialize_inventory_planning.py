from django.core.management.base import BaseCommand

from integracao.services.materialization import PlanningEventMaterializer


class Command(BaseCommand):
    help = "Materializa eventos PAI já sincronizados após configurar os bindings."

    def handle(self, *args, **options):
        materialized, pending = PlanningEventMaterializer().materialize_all()
        self.stdout.write(
            self.style.SUCCESS(
                f"Inventários criados={materialized}; eventos pendentes={pending}."
            )
        )

