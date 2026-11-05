from django.core.management.base import BaseCommand

from estoque.models import ComunicadoEntrega


class Command(BaseCommand):
    help = 'Reagenda entregas que falharam definitivamente.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument(
            '--canal',
            default='TODOS',
            choices=(
                'TODOS',
                ComunicadoEntrega.Canal.EMAIL,
                ComunicadoEntrega.Canal.WHATSAPP,
            ),
        )

    def handle(self, *args, **options):
        canais = (
            (ComunicadoEntrega.Canal.EMAIL, ComunicadoEntrega.Canal.WHATSAPP)
            if options['canal'] == 'TODOS'
            else (options['canal'],)
        )
        ids = list(
            ComunicadoEntrega.objects.filter(
                canal__in=canais,
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

