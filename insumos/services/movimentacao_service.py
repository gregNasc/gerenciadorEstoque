from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from insumos.models import (MovimentacaoInsumo, HistoricoInsumo, Insumo,)

class MovimentacaoService:

    @staticmethod
    def saldo(base, insumo):

        entradas = (
            MovimentacaoInsumo.objects
            .filter(
                base=base,
                insumo=insumo,
                tipo__in=['ENTRADA', 'DEVOLUCAO', 'AJUSTE_ENTRADA']
            )
            .aggregate(total=Sum('quantidade'))
            ['total']
            or Decimal('0')
        )

        saidas = (
            MovimentacaoInsumo.objects
            .filter(
                base=base,
                insumo=insumo,
                tipo__in=['SAIDA', 'PERDA', 'AJUSTE_SAIDA']
            )
            .aggregate(total=Sum('quantidade'))
            ['total']
            or Decimal('0')
        )

        return entradas - saidas

    @staticmethod
    @transaction.atomic
    def entrada(*, base, insumo, quantidade, usuario, valor_unitario, observacao='', solicitacao=None,):

        quantidade = Decimal(str(quantidade))
        valor_unitario = Decimal(str(valor_unitario))
        saldo_anterior = MovimentacaoService.saldo(base, insumo)
        custo_anterior = insumo.valor_medio
        saldo_final = saldo_anterior + quantidade

        if saldo_final > 0:

            novo_custo = ((saldo_anterior * custo_anterior)+(quantidade * valor_unitario)) / saldo_final

        else:

            novo_custo = valor_unitario

        movimentacao = MovimentacaoInsumo.objects.create(
            base=base,
            insumo=insumo,
            tipo='ENTRADA',
            quantidade=quantidade,
            valor_unitario=valor_unitario,
            solicitacao=solicitacao,
            usuario=usuario,
            observacao=observacao,
        )

        insumo.valor_medio = novo_custo
        insumo.save(
            update_fields=['valor_medio']
        )
        HistoricoInsumo.objects.create(

            tipo='MOVIMENTACAO',
            usuario=usuario,
            descricao=(
                f'Entrada de {quantidade} '
                f'{insumo.unidade_medida}'
            ),
            dados={
                'base': base.nome,
                'insumo': insumo.descricao,
                'tipo': 'ENTRADA',
                'quantidade': str(quantidade),
                'valor_unitario': str(valor_unitario),
            }
        )

        return movimentacao

    @staticmethod
    @transaction.atomic
    def saida(*, base, insumo, quantidade, usuario, observacao='', solicitacao=None,):

        quantidade = Decimal(str(quantidade))
        saldo = MovimentacaoService.saldo(base, insumo)

        if saldo < quantidade:

            raise ValueError(
                f'Estoque insuficiente. '
                f'Saldo atual: {saldo}'
            )

        movimentacao = MovimentacaoInsumo.objects.create(
            base=base,
            insumo=insumo,
            tipo='SAIDA',
            quantidade=quantidade,
            valor_unitario=insumo.valor_medio,
            solicitacao=solicitacao,
            usuario=usuario,
            observacao=observacao,
        )

        HistoricoInsumo.objects.create(
            tipo='MOVIMENTACAO',
            usuario=usuario,
            descricao=(
                f'Saída de {quantidade} '
                f'{insumo.unidade_medida}'
            ),
            dados={
                'base': base.nome,
                'insumo': insumo.descricao,
                'tipo': 'SAIDA',
                'quantidade': str(quantidade),
            }
        )

        return movimentacao

    @staticmethod
    @transaction.atomic
    def devolucao(*, base, insumo, quantidade, usuario, observacao='',):

        quantidade = Decimal(str(quantidade))
        movimentacao = MovimentacaoInsumo.objects.create(
            base=base.nome,
            insumo=insumo,
            tipo='DEVOLUCAO',
            quantidade=quantidade,
            valor_unitario=insumo.valor_medio,
            usuario=usuario,
            observacao=observacao,
        )

        return movimentacao

    @staticmethod
    @transaction.atomic
    def perda(*, base, insumo, quantidade, usuario, observacao='',):

        quantidade = Decimal(str(quantidade))
        saldo = MovimentacaoService.saldo(base, insumo)

        if saldo < quantidade:

            raise ValueError(
                'Saldo insuficiente.'
            )

        movimentacao = MovimentacaoInsumo.objects.create(
            base=base.nome,
            insumo=insumo,
            tipo='PERDA',
            quantidade=quantidade,
            valor_unitario=insumo.valor_medio,
            usuario=usuario,
            observacao=observacao,
        )

        return movimentacao

    @staticmethod
    @transaction.atomic
    def ajuste(*, base, insumo, saldo_real, usuario, observacao='',):

        saldo_real = Decimal(str(saldo_real))
        saldo_sistema = MovimentacaoService.saldo(base, insumo)
        diferenca = saldo_real - saldo_sistema

        if diferenca < 0 and saldo_sistema < abs(diferenca):
            raise ValueError(
                'O ajuste de saída excede o saldo disponível.'
            )

            return None

        tipo = (
            'AJUSTE_ENTRADA'
            if diferenca > 0
            else 'AJUSTE_SAIDA'
        )

        movimentacao = MovimentacaoInsumo.objects.create(
            base=base.nome,
            insumo=insumo,
            tipo=tipo,
            quantidade=abs(diferenca),
            valor_unitario=insumo.valor_medio,
            usuario=usuario,
            observacao=(
                f'{observacao}\n'
                f'Saldo sistema: {saldo_sistema}\n'
                f'Saldo real: {saldo_real}'
            ),
        )

        HistoricoInsumo.objects.create(
            tipo='MOVIMENTACAO',
            usuario=usuario,
            descricao=(
                f'Ajuste de estoque: '
                f'{"entrada" if diferenca > 0 else "saída"} '
                f'de {abs(diferenca)} '
                f'{insumo.unidade_medida}'
            ),
            dados={
                'base': base,
                'insumo': insumo.descricao,
                'saldo_sistema': str(saldo_sistema),
                'saldo_real': str(saldo_real),
                'diferenca': str(abs(diferenca)),
                'tipo_ajuste': tipo,
            }
        )

        return movimentacao