import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from estoque.models import ComunicadoEntrega
from estoque.services.comunicacoes.outbox_service import OutboxService


class Command(BaseCommand):
    help = 'Executa continuamente a fila externa de e-mail e WhatsApp.'

    def add_arguments(self, parser):
        parser.add_argument('--intervalo', type=int, default=15)
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument(
            '--max-ciclos',
            type=int,
            default=0,
            help='Zero mantém o worker contínuo; valor positivo é útil em testes.',
        )

    def handle(self, *args, **options):
        intervalo = max(5, options['intervalo'])
        limite = max(1, options['limit'])
        max_ciclos = max(0, options['max_ciclos'])
        ciclo = 0
        self.stdout.write('Worker de comunicações iniciado.')
        try:
            while True:
                close_old_connections()
                total = 0
                for canal in (
                    ComunicadoEntrega.Canal.EMAIL,
                    ComunicadoEntrega.Canal.WHATSAPP,
                ):
                    total += len(OutboxService.processar(
                        canal=canal,
                        limit=limite,
                    ))
                ciclo += 1
                if total:
                    self.stdout.write(
                        f'Ciclo {ciclo}: {total} entrega(s) processada(s).'
                    )
                if max_ciclos and ciclo >= max_ciclos:
                    break
                time.sleep(intervalo)
        except KeyboardInterrupt:
            self.stdout.write('Worker de comunicações encerrado com segurança.')
        finally:
            close_old_connections()
