from decimal import Decimal
from django.db.models import (Sum, Count, F, ExpressionWrapper, DecimalField)
from django.utils import timezone
from insumos.models import (ConsumoInsumo, MovimentacaoInsumo, SolicitacaoInsumo, Inventario, Insumo)
from insumos.services.movimentacao_service import MovimentacaoService

class DashboardService:

    @staticmethod
    def estoque_critico(base=None):

        queryset = Insumo.objects.filter(ativo=True)

        dados = []

        for insumo in queryset:

            saldo_total = Decimal('0')
            bases = (
                [base]
                if base
                else insumo.movimentacaoinsumo_set
                     .values_list(
                        'base',
                        flat=True
                     )
                     .distinct()
            )

            for b in bases:

                saldo_total += (
                    MovimentacaoService.saldo(
                        b,
                        insumo
                    )
                )

            if saldo_total <= insumo.estoque_minimo:

                dados.append({
                    'insumo': insumo,
                    'saldo': saldo_total,
                    'minimo': insumo.estoque_minimo,
                })

        return dados

    @staticmethod
    def saude_estoque(base):

        total = 0
        saudavel = 0
        alerta = 0
        critico = 0

        for insumo in Insumo.objects.filter(
            ativo=True
        ):
            saldo = (MovimentacaoService.saldo(base, insumo))
            total += 1

            if saldo <= insumo.estoque_minimo:
                critico += 1

            elif (
                insumo.estoque_maximo
                and saldo >= insumo.estoque_maximo
            ):
                alerta += 1

            else:
                saudavel += 1

        return {
            'total': total,
            'saudavel': saudavel,
            'alerta': alerta,
            'critico': critico,
        }

    @staticmethod
    def custo_por_cliente():

        return (
            ConsumoInsumo.objects
            .values(
                'inventario__cliente__sigla',
                'inventario__cliente__nome',
            )
            .annotate(
                total=Sum(
                    'valor_total'
                )
            )
            .order_by('-total')
        )

    @staticmethod
    def custo_por_base():

        return (
            ConsumoInsumo.objects
            .values(
                'inventario__base__sigla'
            )
            .annotate(
                total=Sum(
                    'valor_total'
                )
            )
            .order_by('-total')
        )

    @staticmethod
    def inventarios_maior_custo(limite=10):

        return (
            ConsumoInsumo.objects
            .values(
                'inventario_id',
                'inventario__cliente__sigla',
                'inventario__loja',
            )
            .annotate(
                total=Sum(
                    'valor_total'
                )
            )
            .order_by('-total')[:limite]
        )

    @staticmethod
    def perdas_periodo(data_inicio, data_fim):

        return (
            MovimentacaoInsumo.objects
            .filter(
                tipo='PERDA',
                criado_em__date__range=(
                    data_inicio,
                    data_fim,
                )
            )
            .aggregate(
                total=Sum(
                    ExpressionWrapper(
                        F('quantidade')
                        * F('valor_unitario'),
                        output_field=DecimalField(
                            max_digits=15,
                            decimal_places=2,
                        )
                    )
                )
            )['total']
            or Decimal('0')
        )

    @staticmethod
    def solicitacoes_pendentes():

        return (
            SolicitacaoInsumo.objects
            .filter(
                status='PENDENTE'
            )
            .count()
        )

    @staticmethod
    def consumo_mensal(ano):

        return (
            ConsumoInsumo.objects
            .filter(
                inventario__data_inicio__year=ano
            )
            .values(
                'inventario__data_inicio__month'
            )
            .annotate(
                total=Sum(
                    'valor_total'
                )
            )
            .order_by(
                'inventario__data_inicio__month'
            )
        )

    @staticmethod
    def top_insumos(limite=10):

        return (
            ConsumoInsumo.objects
            .values(
                'insumo__descricao',
                'insumo__categoria__nome',
            )
            .annotate(
                quantidade=Sum(
                    'quantidade'
                ),
                valor=Sum(
                    'valor_total'
                )
            )
            .order_by('-valor')[:limite]
        )