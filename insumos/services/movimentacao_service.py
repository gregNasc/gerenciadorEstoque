from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from insumos.models import HistoricoInsumo, MovimentacaoInsumo, SaldoInsumoBase
from insumos.services.saldo_service import SaldoInsumoService

class MovimentacaoService:

    @staticmethod
    def _emitir_ordem_servico(movimentacao, usuario):
        from ordens_servico.services import OrdemServicoService
        OrdemServicoService.para_movimentacao_insumo(movimentacao, usuario)

    @staticmethod
    def saldo(base, insumo):

        materializado = SaldoInsumoBase.objects.filter(base=base, insumo=insumo).first()
        if materializado:
            return materializado.saldo

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
        if quantidade <= 0:
            raise ValueError('A quantidade de entrada deve ser positiva.')
        if valor_unitario < 0:
            raise ValueError('O valor unitário não pode ser negativo.')
        saldo_base = SaldoInsumoService.bloquear(base, insumo)

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

        SaldoInsumoService.aplicar_entrada(
            saldo_base,
            quantidade,
            valor_unitario,
            quando=movimentacao.criado_em,
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

        MovimentacaoService._emitir_ordem_servico(movimentacao, usuario)

        return movimentacao

    @staticmethod
    @transaction.atomic
    def saida(*, base, insumo, quantidade, usuario, observacao='', solicitacao=None,):

        quantidade = Decimal(str(quantidade))
        if quantidade <= 0:
            raise ValueError('A quantidade de saída deve ser positiva.')
        saldo_base = SaldoInsumoService.bloquear(base, insumo)
        saldo = saldo_base.saldo - saldo_base.saldo_reservado

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
            valor_unitario=saldo_base.custo_medio,
            solicitacao=solicitacao,
            usuario=usuario,
            observacao=observacao,
        )

        SaldoInsumoService.aplicar_saida(saldo_base, quantidade)

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

        MovimentacaoService._emitir_ordem_servico(movimentacao, usuario)

        return movimentacao

    @staticmethod
    @transaction.atomic
    def devolucao(*, base, insumo, quantidade, usuario, observacao='',):

        quantidade = Decimal(str(quantidade))
        if quantidade <= 0:
            raise ValueError('A quantidade devolvida deve ser positiva.')
        saldo_base = SaldoInsumoService.bloquear(base, insumo)
        movimentacao = MovimentacaoInsumo.objects.create(
            base=base,
            insumo=insumo,
            tipo='DEVOLUCAO',
            quantidade=quantidade,
            valor_unitario=saldo_base.custo_medio,
            usuario=usuario,
            observacao=observacao,
        )

        SaldoInsumoService.aplicar_entrada(
            saldo_base,
            quantidade,
            saldo_base.custo_medio,
            quando=movimentacao.criado_em,
        )

        MovimentacaoService._emitir_ordem_servico(movimentacao, usuario)

        return movimentacao

    @staticmethod
    @transaction.atomic
    def perda(*, base, insumo, quantidade, usuario, observacao='',):

        quantidade = Decimal(str(quantidade))
        if quantidade <= 0:
            raise ValueError('A quantidade perdida deve ser positiva.')
        saldo_base = SaldoInsumoService.bloquear(base, insumo)
        saldo = saldo_base.saldo - saldo_base.saldo_reservado

        if saldo < quantidade:

            raise ValueError('Saldo insuficiente.')

        movimentacao = MovimentacaoInsumo.objects.create(
            base=base,
            insumo=insumo,
            tipo='PERDA',
            quantidade=quantidade,
            valor_unitario=saldo_base.custo_medio,
            usuario=usuario,
            observacao=observacao,
        )

        SaldoInsumoService.aplicar_saida(saldo_base, quantidade)

        MovimentacaoService._emitir_ordem_servico(movimentacao, usuario)

        return movimentacao

    @staticmethod
    @transaction.atomic
    def ajuste(*, base, insumo, saldo_real, usuario, observacao='',):

        saldo_real = Decimal(str(saldo_real))
        if saldo_real < 0:
            raise ValueError('O saldo real não pode ser negativo.')
        saldo_base = SaldoInsumoService.bloquear(base, insumo)
        saldo_sistema = saldo_base.saldo
        diferenca = saldo_real - saldo_sistema

        if diferenca == 0:
            return None

        if diferenca < 0 and saldo_sistema < abs(diferenca):
            raise ValueError(
                'O ajuste de saída excede o saldo disponível.'
            )

        tipo = ('AJUSTE_ENTRADA'
            if diferenca > 0
            else 'AJUSTE_SAIDA'
        )

        movimentacao = MovimentacaoInsumo.objects.create(
            base=base,
            insumo=insumo,
            tipo=tipo,
            quantidade=abs(diferenca),
            valor_unitario=saldo_base.custo_medio,
            usuario=usuario,
            observacao=(
                f'{observacao}\n'
                f'Saldo sistema: {saldo_sistema}\n'
                f'Saldo real: {saldo_real}'
            ),
        )

        if diferenca > 0:
            SaldoInsumoService.aplicar_entrada(
                saldo_base,
                diferenca,
                saldo_base.custo_medio,
                quando=movimentacao.criado_em,
            )
        elif diferenca < 0:
            SaldoInsumoService.aplicar_saida(saldo_base, abs(diferenca))

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
                'base_id': base.id,
                'base_nome': base.nome,
                'insumo': insumo.descricao,
                'saldo_sistema': str(saldo_sistema),
                'saldo_real': str(saldo_real),
                'diferenca': str(abs(diferenca)),
                'tipo_ajuste': tipo,
            }
        )

        MovimentacaoService._emitir_ordem_servico(movimentacao, usuario)

        return movimentacao
