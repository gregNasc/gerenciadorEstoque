from django.core.management.base import BaseCommand

from estoque.models import ComunicadoEntrega
from estoque.services.comunicacoes.outbox_service import OutboxService


class Command(BaseCommand):
    help = 'Processa entregas externas pendentes dos comunicados.'

    def add_arguments(self, parser):
        parser.add_argument('--canal', default='WHATSAPP', choices=ComunicadoEntrega.Canal.values)
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        ids = OutboxService.processar(canal=options['canal'], limit=max(1, options['limit']))
        self.stdout.write(self.style.SUCCESS(f'{len(ids)} entrega(s) processada(s).'))

