from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Sum, Value, When
from django.db.models.functions import TruncMonth

from insumos.models import ConsumoInsumo, MovimentacaoInsumo


class CustoInsumoService:
    ENTRADAS = ('ENTRADA', 'DEVOLUCAO', 'AJUSTE_ENTRADA')
    SAIDAS = ('SAIDA', 'PERDA', 'AJUSTE_SAIDA')

    @staticmethod
    def pode_visualizar(user):
        perfil = getattr(user, "perfil", None)

        return bool(
            user.is_authenticated
            and perfil
            and (
                    perfil.is_compras_insumos
                    or perfil.is_financeiro_insumos
                    or perfil.is_executivo_insumos
            )
        )

    @classmethod
    def queryset(cls, user):
        if not cls.pode_visualizar(user):
            return ConsumoInsumo.objects.none()
        return ConsumoInsumo.objects.select_related(
            'inventario__cliente', 'inventario__base', 'insumo__categoria'
        )

    @classmethod
    def filtrar(
        cls,
        user,
        *,
        inicio=None,
        fim=None,
        cliente=None,
        loja='',
        tipo='',
        pessoas=None,
        bases=None,
        inventario_id=None,
    ):
        qs = cls.queryset(user)
        if inicio:
            qs = qs.filter(inventario__data_inicio__gte=inicio)
        if fim:
            qs = qs.filter(inventario__data_inicio__lte=fim)
        if cliente:
            qs = qs.filter(inventario__cliente=cliente)
        if loja:
            qs = qs.filter(inventario__loja__iexact=str(loja).strip())
        if tipo:
            qs = qs.filter(inventario__tipo__iexact=tipo)
        if pessoas is not None:
            qs = qs.filter(inventario__pessoas=pessoas)
        if bases is not None:
            qs = qs.filter(inventario__base__in=bases)
        if inventario_id:
            qs = qs.filter(inventario_id=inventario_id)
        return qs

    @staticmethod
    def por_inventario(qs, limite=None):
        dados = list(
            qs.values(
                'inventario_id',
                'inventario__cliente__sigla',
                'inventario__loja',
                'inventario__base__nome',
                'inventario__data_inicio',
                'inventario__tipo',
                'inventario__pessoas',
            )
            .annotate(
                quantidade=Sum('quantidade'),
                total=Sum('valor_total'),
                itens=Count('insumo_id', distinct=True),
            )
            .order_by('-total', 'inventario__data_inicio')
        )
        for item in dados:
            pessoas = item['inventario__pessoas'] or 0
            item['custo_por_pessoa'] = (
                item['total'] / pessoas if pessoas else None
            )
        return dados[:limite] if limite else dados

    @classmethod
    def resumo(cls, qs):
        inventarios = cls.por_inventario(qs)
        total = sum((item['total'] or Decimal('0')) for item in inventarios)
        total_pessoas = sum((item['inventario__pessoas'] or 0) for item in inventarios)
        return {
            'total': total,
            'inventarios': len(inventarios),
            'pessoas': total_pessoas,
            'quantidade': qs.aggregate(total=Sum('quantidade'))['total'] or Decimal('0'),
            'custo_medio_inventario': total / len(inventarios) if inventarios else Decimal('0'),
            'custo_medio_pessoa': total / total_pessoas if total_pessoas else Decimal('0'),
        }

    @staticmethod
    def por_cliente(qs, limite=10):
        return list(
            qs.values('inventario__cliente__sigla', 'inventario__cliente__nome')
            .annotate(
                total=Sum('valor_total'),
                inventarios=Count('inventario_id', distinct=True),
            )
            .order_by('-total')[:limite]
        )

    @staticmethod
    def por_tipo(qs):
        return list(
            qs.values('inventario__tipo')
            .annotate(total=Sum('valor_total'), inventarios=Count('inventario_id', distinct=True))
            .order_by('-total')
        )

    @staticmethod
    def por_mes(qs):
        return list(
            qs.annotate(mes=TruncMonth('inventario__data_inicio'))
            .values('mes')
            .annotate(total=Sum('valor_total'))
            .order_by('mes')
        )

    @staticmethod
    def top_insumos(qs, limite=10):
        return list(
            qs.values('insumo__descricao', 'insumo__categoria__nome')
            .annotate(quantidade=Sum('quantidade'), total=Sum('valor_total'))
            .order_by('-total')[:limite]
        )

    @classmethod
    def valor_estoque_atual(cls, user, bases=None):
        if not cls.pode_visualizar(user):
            return Decimal('0')
        queryset = MovimentacaoInsumo.objects.all()
        if bases is not None:
            queryset = queryset.filter(base__in=bases)
        movimentos = (
            queryset.values('insumo_id', 'insumo__valor_medio')
            .annotate(
                entradas=Sum(Case(
                    When(tipo__in=cls.ENTRADAS, then=F('quantidade')),
                    default=Value(Decimal('0')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )),
                saidas=Sum(Case(
                    When(tipo__in=cls.SAIDAS, then=F('quantidade')),
                    default=Value(Decimal('0')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )),
            )
        )
        total = Decimal('0')
        for item in movimentos:
            saldo = (item['entradas'] or Decimal('0')) - (item['saidas'] or Decimal('0'))
            if saldo > 0:
                total += saldo * (item['insumo__valor_medio'] or Decimal('0'))
        return total
