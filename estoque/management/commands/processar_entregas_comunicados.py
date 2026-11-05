from django.core.management.base import BaseCommand

from estoque.models import ComunicadoEntrega
from estoque.services.comunicacoes.outbox_service import OutboxService


class Command(BaseCommand):
    help = 'Processa entregas externas pendentes dos comunicados.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--canal',
            default='TODOS',
            choices=(
                'TODOS',
                ComunicadoEntrega.Canal.EMAIL,
                ComunicadoEntrega.Canal.WHATSAPP,
            ),
        )
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        canais = (
            (ComunicadoEntrega.Canal.EMAIL, ComunicadoEntrega.Canal.WHATSAPP)
            if options['canal'] == 'TODOS'
            else (options['canal'],)
        )
        total = 0
        for canal in canais:
            ids = OutboxService.processar(
                canal=canal,
                limit=max(1, options['limit']),
            )
            total += len(ids)
            self.stdout.write(f'{canal}: {len(ids)} entrega(s).')
        self.stdout.write(self.style.SUCCESS(f'{total} entrega(s) processada(s).'))

