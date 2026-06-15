from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from insumos.models import (SolicitacaoInsumo, ItemSolicitacaoInsumo, MovimentacaoInsumo,)

class SolicitacaoService:

    @staticmethod
    @transaction.atomic
    def criar_solicitacao(base, solicitante, justificativa, itens, protocolo,):

        solicitacao = SolicitacaoInsumo.objects.create(
            protocolo=protocolo,
            base=base,
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

        ItemSolicitacaoInsumo.objects.bulk_create(objetos)

        return solicitacao

    @staticmethod
    @transaction.atomic
    def aprovar(solicitacao, usuario):

        if solicitacao.status != 'PENDENTE':

            raise ValueError(
                'Somente solicitações pendentes podem ser aprovadas.'
            )

        solicitacao.status = 'APROVADA'
        solicitacao.aprovado_por = usuario
        solicitacao.aprovado_em = timezone.now()

        solicitacao.save(
            update_fields=[
                'status',
                'aprovado_por',
                'aprovado_em',
            ]
        )

        return solicitacao

    @staticmethod
    @transaction.atomic
    def reprovar(solicitacao, usuario, motivo):

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
    def finalizar(solicitacao, usuario):

        if solicitacao.status != 'APROVADA':

            raise ValueError(
                'Solicitação precisa estar aprovada.'
            )

        solicitacao.status = 'FINALIZADA'
        solicitacao.finalizado_por = usuario
        solicitacao.finalizado_em = timezone.now()
        solicitacao.save(
            update_fields=['status']
        )

        return solicitacao