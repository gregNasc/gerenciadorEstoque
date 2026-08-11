from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from insumos.models import MovimentacaoInsumo, SaldoInsumoBase
from insumos.services.saldo_service import SaldoInsumoService


class Command(BaseCommand):
    help = 'Reconstrói saldos e custos médios por base de forma idempotente.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        pares = list(
            MovimentacaoInsumo.objects.values_list('base_id', 'insumo_id')
            .distinct()
            .order_by('base_id', 'insumo_id')
        )
        divergencias = 0
        for base_id, insumo_id in pares:
            movimentos = MovimentacaoInsumo.objects.filter(
                base_id=base_id,
                insumo_id=insumo_id,
            )
            try:
                saldo, custo, ultima_entrada = SaldoInsumoService.calcular(movimentos)
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            atual = SaldoInsumoBase.objects.filter(
                base_id=base_id,
                insumo_id=insumo_id,
            ).first()
            if not atual or atual.saldo != saldo or atual.custo_medio != custo:
                divergencias += 1
            if not options['dry_run']:
                SaldoInsumoBase.objects.update_or_create(
                    base_id=base_id,
                    insumo_id=insumo_id,
                    defaults={
                        'saldo': saldo,
                        'custo_medio': custo,
                        'ultima_entrada_em': ultima_entrada,
                    },
                )
        if options['dry_run']:
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(
            f'Pares analisados: {len(pares)} | divergências: {divergencias} | '
            f'modo: {"simulação" if options["dry_run"] else "gravação"}'
        ))
