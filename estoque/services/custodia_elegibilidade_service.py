from __future__ import annotations

from django.db.models import Exists, OuterRef

from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)
from estoque.models import Empresa, Equipamento, LinhaMovel


class CustodiaElegibilidadeService:
    """Resolve ativos individualizados elegíveis sem depender de seus nomes."""

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

        capacidade_ativa = CapacidadeCatalogoProdutoEmpresa.objects.filter(
            catalogo__empresa_id=empresa_id,
            catalogo__produto_id=OuterRef('produto_id'),
            catalogo__ativo=True,
            codigo=cls.CAPACIDADE,
            ativa=True,
        )
        return queryset.filter(
            regional__empresa_id=empresa_id,
            produto_id__isnull=False,
        ).annotate(
            possui_capacidade_custodia=Exists(capacidade_ativa),
        ).filter(possui_capacidade_custodia=True)

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
