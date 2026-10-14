from __future__ import annotations

from estoque.models import Equipamento, ItemCustodia


class CustodiaResponsavelLegadoService:
    """Mantém o campo livre legado compatível sem adotá-lo como fonte de verdade."""

    @staticmethod
    def item_vigente(equipamento):
        if not equipamento or not getattr(equipamento, 'pk', None):
            return None
        return (
            ItemCustodia.objects
            .filter(equipamento_id=equipamento.pk, vigente=True)
            .select_related('custodia__colaborador')
            .first()
        )

    @classmethod
    def responsavel_atual(cls, equipamento):
        item = cls.item_vigente(equipamento)
        if item is not None:
            return item.custodia.colaborador.nome
        return str(getattr(equipamento, 'responsavel', '') or '')

    @classmethod
    def sincronizar_custodia(cls, custodia, *, responsaveis_liberaveis=()):
        if not custodia or not getattr(custodia, 'pk', None):
            return
        equipamento_ids = list(
            ItemCustodia.objects.filter(
                custodia_id=custodia.pk,
                equipamento_id__isnull=False,
            ).values_list('equipamento_id', flat=True)
        )
        if not equipamento_ids:
            return

        liberaveis = {
            str(nome or '').strip().casefold()
            for nome in responsaveis_liberaveis
            if str(nome or '').strip()
        }
        nome_atual = str(custodia.colaborador.nome or '').strip()
        liberaveis.add(nome_atual.casefold())

        for equipamento in Equipamento.objects.filter(pk__in=equipamento_ids):
            item_vigente = cls.item_vigente(equipamento)
            if item_vigente is not None:
                responsavel = item_vigente.custodia.colaborador.nome
                if equipamento.responsavel != responsavel:
                    Equipamento.objects.filter(pk=equipamento.pk).update(
                        responsavel=responsavel,
                    )
                continue

            responsavel_legado = str(equipamento.responsavel or '').strip()
            if responsavel_legado.casefold() in liberaveis:
                Equipamento.objects.filter(pk=equipamento.pk).update(
                    responsavel='',
                )
