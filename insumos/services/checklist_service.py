from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from insumos.models import (ChecklistDiario, ItemChecklist, HistoricoInsumo,)
from insumos.services.movimentacao_service import MovimentacaoService
from insumos.services.consumo_service import ConsumoService

class ChecklistService:

    @staticmethod
    @transaction.atomic
    def criar(*, inventario, data, responsavel, observacao=''):

        checklist, criado = ChecklistDiario.objects.get_or_create(
            inventario=inventario,
            data=data,
            defaults={
                'responsavel': responsavel,
                'observacao': observacao,
            }
        )

        return checklist

    @staticmethod
    @transaction.atomic
    def adicionar_item(*, checklist, insumo, quantidade_enviada,):

        item, criado = ItemChecklist.objects.get_or_create(
            checklist=checklist,
            insumo=insumo,
            defaults={
                'quantidade_enviada': quantidade_enviada,
            }
        )

        if not criado:

            raise ValueError(
                'Este insumo já foi adicionado.'
            )

        return item

    @staticmethod
    @transaction.atomic
    def atualizar_item(*, item, utilizada, retornada, perdida,):

        utilizada = Decimal(str(utilizada))
        retornada = Decimal(str(retornada))
        perdida = Decimal(str(perdida))
        total = utilizada + retornada + perdida

        if total > item.quantidade_enviada:

            raise ValueError(
                'A soma não pode exceder a quantidade enviada.'
            )

        item.quantidade_utilizada = utilizada
        item.quantidade_retornada = retornada
        item.quantidade_perdida = perdida
        item.save(
            update_fields=[
                'quantidade_utilizada',
                'quantidade_retornada',
                'quantidade_perdida',
            ]
        )

        return item

    @staticmethod
    @transaction.atomic
    def finalizar(*, checklist, usuario,):

        if checklist.finalizado:
            raise ValueError('Checklist já finalizado.')

        if not checklist.itens.exists():
            raise ValueError('Checklist sem itens.')

        base = checklist.inventario.base

        for item in checklist.itens.select_related('insumo'):

            total = (
                    item.quantidade_utilizada
                    + item.quantidade_retornada
                    + item.quantidade_perdida
            )

            if total != item.quantidade_enviada:
                raise ValueError(
                    f'O item "{item.insumo.descricao}" '
                    f'não está conciliado.\n'
                    f'Enviado: {item.quantidade_enviada}\n'
                    f'Apurado: {total}'
                )

            if (
                    item.insumo.tipo_controle == 'LOTE'
                    and item.quantidade_perdida > 0
            ):
                raise ValueError(
                    f'O insumo "{item.insumo.descricao}" '
                    'possui controle por lote. '
                    'Registre a perda utilizando MovimentacaoTag.'
                )

            if item.quantidade_enviada > 0:

                MovimentacaoService.saida(
                    base=base,
                    insumo=item.insumo,
                    quantidade=item.quantidade_enviada,
                    usuario=usuario,
                    observacao=(
                        f'Checklist {checklist.id}'
                    )
                )

            if item.quantidade_retornada > 0:

                MovimentacaoService.devolucao(
                    base=base,
                    insumo=item.insumo,
                    quantidade=item.quantidade_retornada,
                    usuario=usuario,
                    observacao=(
                        f'Checklist {checklist.id}'
                    )
                )

            if item.quantidade_perdida > 0:

                MovimentacaoService.perda(
                    base=base,
                    insumo=item.insumo,
                    quantidade=item.quantidade_perdida,
                    usuario=usuario,
                    observacao=(
                        f'Checklist {checklist.id}'
                    )
                )

            if item.quantidade_utilizada > 0:

                ConsumoService.gerar(item=item)

        HistoricoInsumo.objects.create(
            tipo='CHECKLIST',
            usuario=usuario,
            descricao=(
                f'Checklist diário do inventário '
                f'{checklist.inventario.sigla} '
                f'finalizado.'
            ),

            dados={
                'inventario': checklist.inventario.sigla,
                'cliente': checklist.inventario.cliente,
                'base': checklist.inventario.base.sigla,
                'data': str(checklist.data),
                'itens': checklist.itens.count(),
            }
        )
        from django.utils import timezone
        checklist.finalizado = True
        checklist.finalizado_em = timezone.now()
        checklist.finalizado_por = usuario

        checklist.save(
            update_fields=[
                'finalizado',
                'finalizado_em',
                'finalizado_por',
            ]
        )
        return checklist

