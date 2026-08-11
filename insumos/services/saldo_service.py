from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from estoque.models import Base
from insumos.models import MovimentacaoInsumo, SaldoInsumoBase


class SaldoInsumoService:
    ENTRADAS = {'ENTRADA', 'DEVOLUCAO', 'AJUSTE_ENTRADA'}
    SAIDAS = {'SAIDA', 'PERDA', 'AJUSTE_SAIDA'}

    @classmethod
    def calcular(cls, movimentos):
        saldo = Decimal('0')
        custo = Decimal('0')
        ultima_entrada = None
        for movimento in movimentos.order_by('criado_em', 'pk'):
            quantidade = Decimal(movimento.quantidade)
            valor = Decimal(movimento.valor_unitario or 0)
            if movimento.tipo in cls.ENTRADAS:
                novo_saldo = saldo + quantidade
                if quantidade > 0 and valor > 0 and novo_saldo > 0:
                    custo = ((saldo * custo) + (quantidade * valor)) / novo_saldo
                saldo = novo_saldo
                ultima_entrada = movimento.criado_em
            elif movimento.tipo in cls.SAIDAS:
                saldo -= quantidade
                if saldo < 0:
                    raise ValueError(
                        f'Saldo histórico negativo após a movimentação {movimento.pk}.'
                    )
        return saldo, custo, ultima_entrada

    @classmethod
    def reconstruir_par(cls, base, insumo, *, salvar=True):
        movimentos = MovimentacaoInsumo.objects.filter(base=base, insumo=insumo)
        saldo, custo, ultima_entrada = cls.calcular(movimentos)
        if not salvar:
            return saldo, custo, ultima_entrada
        registro, _ = SaldoInsumoBase.objects.update_or_create(
            base=base,
            insumo=insumo,
            defaults={
                'saldo': saldo,
                'custo_medio': custo,
                'ultima_entrada_em': ultima_entrada,
            },
        )
        return registro

    @classmethod
    def bloquear(cls, base, insumo):
        # O lock da base serializa também a criação do primeiro saldo do par.
        Base.objects.select_for_update().get(pk=base.pk)
        registro = SaldoInsumoBase.objects.select_for_update().filter(
            base=base,
            insumo=insumo,
        ).first()
        if registro:
            return registro
        return cls.reconstruir_par(base, insumo)

    @staticmethod
    def aplicar_entrada(registro, quantidade, valor_unitario, *, quando=None):
        quantidade = Decimal(str(quantidade))
        valor_unitario = Decimal(str(valor_unitario))
        novo_saldo = registro.saldo + quantidade
        if quantidade > 0 and valor_unitario > 0 and novo_saldo > 0:
            registro.custo_medio = (
                (registro.saldo * registro.custo_medio)
                + (quantidade * valor_unitario)
            ) / novo_saldo
        registro.saldo = novo_saldo
        registro.ultima_entrada_em = quando or timezone.now()
        registro.save(update_fields=['saldo', 'custo_medio', 'ultima_entrada_em', 'recalculado_em'])

    @staticmethod
    def aplicar_saida(registro, quantidade):
        quantidade = Decimal(str(quantidade))
        if registro.saldo < quantidade:
            raise ValueError(f'Estoque insuficiente. Saldo atual: {registro.saldo}')
        registro.saldo -= quantidade
        registro.save(update_fields=['saldo', 'recalculado_em'])
