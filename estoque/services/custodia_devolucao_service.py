from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from estoque.models import (
    Custodia,
    DevolucaoCustodia,
    ItemCustodia,
    ItemDevolucaoCustodia,
)


class CustodiaDevolucaoService:
    """Registra devoluções de Custódia com classificação item a item."""

    @classmethod
    def registrar(
        cls,
        *,
        custodia,
        itens,
        motivo,
        responsavel_recebimento,
        registrado_por,
        data_devolucao=None,
        observacao='',
    ):
        if not getattr(custodia, 'pk', None):
            raise ValidationError({'custodia': 'Informe uma Custódia persistida.'})

        itens = list(itens or ())
        if not itens:
            raise ValidationError({'itens': 'Informe a situação de todos os itens.'})

        with transaction.atomic():
            custodia = (
                Custodia.objects.select_for_update()
                .select_related('empresa', 'colaborador')
                .get(pk=custodia.pk)
            )
            if custodia.status not in Custodia.STATUS_VIGENTES:
                raise ValidationError({
                    'custodia': 'Somente uma Custódia vigente pode ser devolvida.',
                })

            pendentes = list(
                ItemCustodia.objects.select_for_update()
                .filter(custodia=custodia, devolvido_em__isnull=True, vigente=True)
                .order_by('pk')
            )
            pendentes_por_id = {item.pk: item for item in pendentes}
            classificados = cls._normalizar_itens(itens, pendentes_por_id)

            ids_informados = set(classificados)
            ids_pendentes = set(pendentes_por_id)
            if ids_informados != ids_pendentes:
                ausentes = sorted(ids_pendentes - ids_informados)
                externos = sorted(ids_informados - ids_pendentes)
                detalhes = []
                if ausentes:
                    detalhes.append(f'itens não classificados: {ausentes}')
                if externos:
                    detalhes.append(f'itens inválidos: {externos}')
                raise ValidationError({
                    'itens': (
                        'Classifique exatamente todos os itens pendentes da Custódia'
                        + (f' ({"; ".join(detalhes)}).' if detalhes else '.')
                    ),
                })

            data_devolucao = data_devolucao or timezone.now()
            devolucao = DevolucaoCustodia(
                custodia=custodia,
                data_devolucao=data_devolucao,
                motivo=motivo,
                observacao=observacao,
                responsavel_recebimento=responsavel_recebimento,
                registrado_por=registrado_por,
            )
            devolucao.save()

            devolvidos = []
            faltantes = []
            for item_id, dados in classificados.items():
                item = pendentes_por_id[item_id]
                registro = ItemDevolucaoCustodia(
                    devolucao=devolucao,
                    item_custodia=item,
                    situacao=dados['situacao'],
                    condicao_devolucao=dados['condicao_devolucao'],
                    observacao=dados['observacao'],
                )
                registro.save()
                if registro.situacao == ItemDevolucaoCustodia.Situacao.DEVOLVIDO:
                    devolvidos.append(item_id)
                else:
                    faltantes.append(item_id)

            if devolvidos:
                ItemCustodia.objects.filter(pk__in=devolvidos).update(
                    devolvido_em=data_devolucao,
                    vigente=False,
                )

            custodia.status = (
                Custodia.Status.EM_DEVOLUCAO
                if faltantes
                else Custodia.Status.FINALIZADA
            )
            custodia.save()
            from estoque.services.termo_devolucao_custodia_service import (
                TermoDevolucaoCustodiaService,
            )

            termo = TermoDevolucaoCustodiaService.gerar(
                devolucao=devolucao,
                usuario=registrado_por,
            )
            from estoque.models import EventoNotificacaoCustodia
            from estoque.services.custodia_notificacao_service import (
                CustodiaNotificacaoService,
            )

            CustodiaNotificacaoService.publicar(
                evento=EventoNotificacaoCustodia.Evento.DEVOLUCAO_REGISTRADA,
                custodia=custodia,
                criado_por=registrado_por,
                devolucao=devolucao,
                termo_devolucao=termo,
            )
            return devolucao

    @staticmethod
    def _normalizar_itens(itens, pendentes_por_id):
        classificados = {}
        for dados in itens:
            item = dados.get('item_custodia') if isinstance(dados, dict) else None
            item_id = getattr(item, 'pk', item)
            try:
                item_id = int(item_id)
            except (TypeError, ValueError):
                raise ValidationError({'itens': 'Item de Custódia inválido.'})
            if item_id in classificados:
                raise ValidationError({'itens': f'Item {item_id} informado em duplicidade.'})

            situacao = str(dados.get('situacao', '')).strip().upper()
            condicao = str(
                dados.get(
                    'condicao_devolucao',
                    Custodia.CondicaoGeral.NAO_INFORMADA,
                )
            ).strip().upper()
            observacao = str(dados.get('observacao', '') or '').strip()

            if situacao not in ItemDevolucaoCustodia.Situacao.values:
                raise ValidationError({'itens': f'Situação inválida para o item {item_id}.'})
            if condicao not in Custodia.CondicaoGeral.values:
                raise ValidationError({'itens': f'Condição inválida para o item {item_id}.'})

            classificados[item_id] = {
                'situacao': situacao,
                'condicao_devolucao': condicao,
                'observacao': observacao,
            }
        return classificados
