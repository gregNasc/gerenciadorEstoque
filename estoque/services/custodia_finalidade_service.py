from __future__ import annotations

from django.db import transaction

from estoque.models import Equipamento, Historico, ItemCustodia


class CustodiaFinalidadeService:
    """Converte para Administrativo os equipamentos entregues em Custódia."""

    @classmethod
    def sincronizar(cls, custodia):
        if (
            not custodia
            or not getattr(custodia, 'pk', None)
            or not custodia.vigente
            or not custodia.registrado_por_id
        ):
            return 0

        equipamento_ids = ItemCustodia.objects.filter(
            custodia_id=custodia.pk,
            equipamento_id__isnull=False,
            vigente=True,
        ).values_list('equipamento_id', flat=True)

        alterados = 0
        with transaction.atomic():
            equipamentos = Equipamento.objects.select_for_update().filter(
                pk__in=equipamento_ids,
                finalidade=Equipamento.Finalidade.OPERACIONAL,
            )
            for equipamento in equipamentos:
                atualizado = Equipamento.objects.filter(
                    pk=equipamento.pk,
                    finalidade=Equipamento.Finalidade.OPERACIONAL,
                ).update(finalidade=Equipamento.Finalidade.ADMINISTRATIVO)
                if not atualizado:
                    continue
                Historico.objects.create(
                    equipamento=equipamento,
                    tipo_acao='EDICAO',
                    usuario=custodia.registrado_por,
                    detalhes={
                        'origem': 'CUSTODIA',
                        'custodia_id': custodia.pk,
                        'colaborador_id': custodia.colaborador_id,
                        'colaborador_nome': custodia.colaborador.nome,
                        'alteracoes': {
                            'finalidade': {
                                'antes': Equipamento.Finalidade.OPERACIONAL,
                                'depois': Equipamento.Finalidade.ADMINISTRATIVO,
                            },
                        },
                        'motivo': (
                            'Alteração automática ao entregar o equipamento '
                            'em Custódia.'
                        ),
                    },
                )
                alterados += 1
        return alterados
