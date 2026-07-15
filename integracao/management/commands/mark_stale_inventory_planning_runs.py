from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from integracao.models import InventoryPlanningSyncRun


class Command(BaseCommand):
    help = "Marca como STALE runs RUNNING abandonados além da idade mínima."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=30)

    def handle(self, *args, **options):
        minutes = options["minutes"]
        if minutes < 30:
            raise CommandError("A idade mínima permitida é 30 minutos.")
        now = timezone.now()
        threshold = now - timedelta(minutes=minutes)
        queryset = InventoryPlanningSyncRun.objects.filter(
            status=InventoryPlanningSyncRun.Status.RUNNING,
            started_at__lt=threshold,
        )
        count = queryset.update(
            status=InventoryPlanningSyncRun.Status.STALE,
            finished_at=now,
            error_code="STALE_RUN",
            error_message=f"Execução abandonada há mais de {minutes} minutos.",
        )
        self.stdout.write(self.style.SUCCESS(f"Runs marcados como STALE: {count}."))
