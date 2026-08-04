from django.core.management.base import BaseCommand

from estoque.models import ComunicadoEntrega


class Command(BaseCommand):
    help = 'Reagenda entregas que falharam definitivamente.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        ids = list(
            ComunicadoEntrega.objects.filter(
                canal=ComunicadoEntrega.Canal.WHATSAPP,
                status=ComunicadoEntrega.Status.FALHA,
                proxima_tentativa_em__isnull=True,
            ).order_by('criada_em').values_list('pk', flat=True)[:max(1, options['limit'])]
        )
        atualizadas = ComunicadoEntrega.objects.filter(pk__in=ids).update(
            status=ComunicadoEntrega.Status.PENDENTE,
            tentativas=0,
            ultimo_erro='',
        )
        self.stdout.write(self.style.SUCCESS(f'{atualizadas} entrega(s) reagendada(s).'))

