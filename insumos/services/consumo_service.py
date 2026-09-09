from decimal import Decimal
from django.db import transaction
from django.db.models import (Sum, F, DecimalField, ExpressionWrapper)
from insumos.models import (ConsumoInsumo, HistoricoInsumo)
from insumos.policies import InsumosTenantPolicy

class ConsumoService:

    @staticmethod
    @transaction.atomic
    def gerar(*, item):

        usuario = item.checklist.finalizado_por or item.checklist.responsavel
        InsumosTenantPolicy.require_base(
            usuario,
            item.checklist.inventario.base,
            resource=InsumosTenantPolicy.SUPPLIES,
            action=InsumosTenantPolicy.MOVE,
        )

        quantidade = item.quantidade_utilizada + item.quantidade_perdida

        if quantidade <= 0:
            return None

        consumo_existente = ConsumoInsumo.objects.filter(item_checklist=item).exists()

        if consumo_existente:
            raise ValueError('Consumo já registrado para este item.')

        if item.insumo.valor_medio is None:
            raise ValueError(f'O insumo "{item.insumo.descricao}" ''não possui valor médio definido.')

        valor_unitario = item.insumo.valor_medio
        valor_total = quantidade * valor_unitario
        consumo = ConsumoInsumo.objects.create(
            inventario=item.checklist.inventario,
            item_checklist=item,
            insumo=item.insumo,
            quantidade=quantidade,
            valor_unitario=valor_unitario,
            valor_total=valor_total,
        )

        HistoricoInsumo.objects.create(
            tipo='CONSUMO',
            usuario=usuario,
            base=item.checklist.inventario.base,
            descricao=(
                f'Consumo registrado para '
                f'{item.insumo.descricao}'
            ),
            dados={
                'inventario': str(item.checklist.inventario),
                'cliente': item.checklist.inventario.cliente.sigla,
                'base': item.checklist.inventario.base.nome,
                'insumo': item.insumo.descricao,
                'quantidade': str(quantidade),
                'quantidade_utilizada': str(item.quantidade_utilizada),
                'quantidade_perdida': str(item.quantidade_perdida),
                'valor_unitario': str(valor_unitario),
                'valor_total': str(valor_total),
            }
        )

        return consumo

    @staticmethod
    def custo_inventario(user, inventario):

        return (
                InsumosTenantPolicy.consumptions(user, ConsumoInsumo.objects)
                .filter(
                    inventario=inventario
                )
                .aggregate(
                    total=Sum('valor_total')
                )['total']
                or Decimal('0')
        )

    @staticmethod
    def custo_cliente(user, cliente):

        return (
                InsumosTenantPolicy.consumptions(user, ConsumoInsumo.objects)
                .filter(
                    inventario__cliente=cliente
                )
                .aggregate(
                    total=Sum('valor_total')
                )['total']
                or Decimal('0')
        )

    @staticmethod
    def custo_por_base(user):

        return (
            InsumosTenantPolicy.consumptions(user, ConsumoInsumo.objects)
            .values(
                'inventario__base__sigla'
            )
            .annotate(
                total=Sum('valor_total')
            )
            .order_by('-total')
        )

    @staticmethod
    def custo_periodo(user, data_inicio, data_fim):

        return (
                InsumosTenantPolicy.consumptions(user, ConsumoInsumo.objects)
                .filter(
                    inventario__data_inicio__gte=data_inicio,
                    inventario__data_inicio__lte=data_fim,
                )
                .aggregate(
                    total=Sum('valor_total')
                )['total']
                or Decimal('0')
        )

    @staticmethod
    def custo_mensal(user, ano):

        return (
            InsumosTenantPolicy.consumptions(user, ConsumoInsumo.objects)
            .filter(
                inventario__data_inicio__year=ano
            )
            .values(
                'inventario__data_inicio__month'
            )
            .annotate(
                total=Sum('valor_total')
            )
            .order_by(
                'inventario__data_inicio__month'
            )
        )

    @staticmethod
    def top_insumos(user, limite=10):

        return (
            InsumosTenantPolicy.consumptions(user, ConsumoInsumo.objects)
            .values(
                'insumo_id',
                'insumo__descricao',
                'insumo__categoria__nome',
            )
            .annotate(
                quantidade=Sum('quantidade'),
                valor=Sum('valor_total'),
            )
            .order_by('-valor')[:limite]
        )

    @staticmethod
    def top_clientes(user, limite=10):

        return (
            InsumosTenantPolicy.consumptions(user, ConsumoInsumo.objects)
            .values(
                'inventario__cliente__sigla',
                'inventario__cliente__nome',
            )
            .annotate(
                total=Sum('valor_total')
            )
            .order_by('-total')[:limite]
        )

    @staticmethod
    def custo_por_categoria(user):

        return (
            InsumosTenantPolicy.consumptions(user, ConsumoInsumo.objects)
            .values(
                'insumo__categoria__nome'
            )
            .annotate(
                total=Sum('valor_total')
            )
            .order_by('-total')
        )

    @staticmethod
    def detalhamento_inventario(user, inventario):

        return (
            InsumosTenantPolicy.consumptions(user, ConsumoInsumo.objects)
            .filter(
                inventario=inventario
            )
            .values(
                'insumo__descricao',
                'insumo__categoria__nome',
            )
            .annotate(
                quantidade=Sum('quantidade'),
                total=Sum('valor_total'),
            )
            .order_by('-total')
        )

    @staticmethod
    def perdas_periodo(user, data_inicio, data_fim):

        from insumos.models import MovimentacaoInsumo
        from django.db.models import (
            F,
            Sum,
            DecimalField,
            ExpressionWrapper,
        )

        return (
                InsumosTenantPolicy.movements(user, MovimentacaoInsumo.objects)
                .filter(
                    tipo='PERDA',
                    criado_em__date__gte=data_inicio,
                    criado_em__date__lte=data_fim,
                )
                .aggregate(
                    total=Sum(
                        ExpressionWrapper(
                            F('quantidade') * F('valor_unitario'),
                            output_field=DecimalField(
                                max_digits=14,
                                decimal_places=2
                            )
                        )
                    )
                )['total']
                or Decimal('0')
        )
