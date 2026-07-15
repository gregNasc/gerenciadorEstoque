from django.core.management.base import BaseCommand

from estoque.services.comunicado_service import ComunicadoService


class Command(BaseCommand):
    help = 'Emite comunicados um dia antes da previsão de retorno de equipamentos em manutenção.'

    def handle(self, *args, **options):
        comunicados = ComunicadoService.notificar_manutencoes_previstas()
        self.stdout.write(self.style.SUCCESS(
            f'{len(comunicados)} comunicado(s) de manutenção emitido(s).'
        ))
