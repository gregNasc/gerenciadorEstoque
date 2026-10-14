from django.core.management.base import BaseCommand

from estoque.models import EntregaNotificacaoCustodia
from estoque.services.custodia_notificacao_outbox import (
    CustodiaNotificacaoOutbox,
)


class Command(BaseCommand):
    help = 'Processa entregas pendentes de e-mail e WhatsApp da Custódia.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--canal',
            choices=(
                EntregaNotificacaoCustodia.Canal.EMAIL,
                EntregaNotificacaoCustodia.Canal.WHATSAPP,
            ),
        )
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        processed = CustodiaNotificacaoOutbox.processar(
            canal=options['canal'],
            limit=max(1, options['limit']),
        )
        self.stdout.write(self.style.SUCCESS(
            f'{len(processed)} entrega(s) processada(s).'
        ))
