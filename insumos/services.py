from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import (SolicitacaoInsumo, ItemSolicitacaoInsumo, MovimentacaoInsumo,)

class MovimentacaoService:

    @staticmethod
    def obter_saldo(regional, insumo):

        entradas = (
            MovimentacaoInsumo.objects
            .filter(
                regional=regional,
                insumo=insumo,
                tipo__in=['ENTRADA', 'DEVOLUCAO', 'AJUSTE']
            )
            .aggregate(total=Sum('quantidade'))['total']
            or Decimal('0')
        )

        saidas = (
            MovimentacaoInsumo.objects
            .filter(
                regional=regional,
                insumo=insumo,
                tipo__in=['SAIDA', 'PERDA']
            )
            .aggregate(total=Sum('quantidade'))['total']
            or Decimal('0')
        )

        return entradas - saidas

    @staticmethod
    @transaction.atomic
    def entrada(
        regional,
        insumo,
        quantidade,
        usuario,
        valor_unitario=Decimal('0'),
        observacao=''
    ):

        return MovimentacaoInsumo.objects.create(
            regional=regional,
            insumo=insumo,
            tipo='ENTRADA',
            quantidade=quantidade,
            valor_unitario=valor_unitario,
            usuario=usuario,
            observacao=observacao,
        )

    @staticmethod
    @transaction.atomic
    def saida(
        regional,
        insumo,
        quantidade,
        usuario,
        observacao=''
    ):

        saldo = MovimentacaoService.obter_saldo(
            regional,
            insumo
        )

        if saldo < quantidade:
            raise ValueError(
                f'Estoque insuficiente. Saldo atual: {saldo}'
            )

        return MovimentacaoInsumo.objects.create(
            regional=regional,
            insumo=insumo,
            tipo='SAIDA',
            quantidade=quantidade,
            usuario=usuario,
            observacao=observacao,
        )

    @staticmethod
    @transaction.atomic
    def devolucao(
        regional,
        insumo,
        quantidade,
        usuario,
        observacao=''
    ):

        return MovimentacaoInsumo.objects.create(
            regional=regional,
            insumo=insumo,
            tipo='DEVOLUCAO',
            quantidade=quantidade,
            usuario=usuario,
            observacao=observacao,
        )

    @staticmethod
    @transaction.atomic
    def perda(
        regional,
        insumo,
        quantidade,
        usuario,
        observacao=''
    ):

        saldo = MovimentacaoService.obter_saldo(
            regional,
            insumo
        )

        if saldo < quantidade:
            raise ValueError(
                f'Saldo insuficiente para registrar perda.'
            )

        return MovimentacaoInsumo.objects.create(
            regional=regional,
            insumo=insumo,
            tipo='PERDA',
            quantidade=quantidade,
            usuario=usuario,
            observacao=observacao,
        )

class SolicitacaoService:

    @staticmethod
    @transaction.atomic
    def criar_solicitacao(
        regional,
        solicitante,
        justificativa,
        itens,
        protocolo,
    ):

        solicitacao = SolicitacaoInsumo.objects.create(
            protocolo=protocolo,
            regional=regional,
            solicitante=solicitante,
            justificativa=justificativa,
        )

        objetos = []

        for item in itens:

            objetos.append(
                ItemSolicitacaoInsumo(
                    solicitacao=solicitacao,
                    insumo=item['insumo'],
                    quantidade=item['quantidade'],
                )
            )

        ItemSolicitacaoInsumo.objects.bulk_create(
            objetos
        )

        return solicitacao

    @staticmethod
    @transaction.atomic
    def aprovar(
        solicitacao,
        usuario
    ):

        if solicitacao.status != 'PENDENTE':

            raise ValueError(
                'Somente solicitações pendentes podem ser aprovadas.'
            )

        solicitacao.status = 'APROVADA'

        solicitacao.save(
            update_fields=['status']
        )

        return solicitacao

    @staticmethod
    @transaction.atomic
    def reprovar(
        solicitacao,
        usuario,
    ):

        if solicitacao.status != 'PENDENTE':

            raise ValueError(
                'Somente solicitações pendentes podem ser reprovadas.'
            )

        solicitacao.status = 'REPROVADA'

        solicitacao.save(
            update_fields=['status']
        )

        return solicitacao

    @staticmethod
    @transaction.atomic
    def finalizar(
        solicitacao,
        usuario
    ):

        if solicitacao.status != 'APROVADA':

            raise ValueError(
                'Solicitação precisa estar aprovada.'
            )

        solicitacao.status = 'FINALIZADA'

        solicitacao.save(
            update_fields=['status']
        )

        return solicitacao

