from __future__ import annotations

from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)
from estoque.models import Empresa, Equipamento, LinhaMovel


class CustodiaElegibilidadeService:
    """Resolve ativos disponíveis no escopo da empresa para Custódia."""

    CAPACIDADE = CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL

    @staticmethod
    def _empresa_id(empresa):
        if isinstance(empresa, Empresa):
            return empresa.pk
        if isinstance(empresa, int) and not isinstance(empresa, bool):
            return empresa
        return None

    @classmethod
    def equipamentos(cls, *, empresa, queryset=None):
        empresa_id = cls._empresa_id(empresa)
        queryset = queryset if queryset is not None else Equipamento.objects.all()
        if not empresa_id:
            return queryset.none()

        # Todo equipamento cadastrado pertence a uma Base por meio de
        # ``regional``. A Base selecionada no formulário restringe a lista e
        # o modelo confirma esse vínculo novamente ao salvar. A elegibilidade
        # não depende do catálogo técnico da empresa.
        return queryset.filter(regional__empresa_id=empresa_id)

    @classmethod
    def linhas_moveis(cls, *, empresa, queryset=None):
        empresa_id = cls._empresa_id(empresa)
        queryset = queryset if queryset is not None else LinhaMovel.objects.all()
        if not empresa_id:
            return queryset.none()

        produto_chip_elegivel = CatalogoProdutoEmpresa.objects.filter(
            empresa_id=empresa_id,
            ativo=True,
            capacidades__codigo=(
                CapacidadeCatalogoProdutoEmpresa.ATIVO_LINHA_MOVEL
            ),
            capacidades__ativa=True,
        ).filter(
            capacidades__codigo=cls.CAPACIDADE,
            capacidades__ativa=True,
        )
        if not produto_chip_elegivel.exists():
            return queryset.none()
        return queryset.filter(empresa_id=empresa_id)

    @classmethod
    def permite(cls, *, empresa, ativo):
        if isinstance(ativo, Equipamento):
            return cls.equipamentos(
                empresa=empresa,
                queryset=Equipamento.objects.filter(pk=ativo.pk),
            ).exists()
        if isinstance(ativo, LinhaMovel):
            return cls.linhas_moveis(
                empresa=empresa,
                queryset=LinhaMovel.objects.filter(pk=ativo.pk),
            ).exists()
        return False
