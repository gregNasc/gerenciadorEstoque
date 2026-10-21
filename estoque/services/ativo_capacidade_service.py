from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)


class AtivoCapacidadeService:
    """Resolve capacidades tenant-aware sem quebrar produtos do catálogo legado."""

    @classmethod
    def habilitada(cls, *, empresa, produto, codigo):
        if not empresa or not produto:
            return False
        configuracao = CapacidadeCatalogoProdutoEmpresa.objects.filter(
            catalogo__empresa=empresa,
            catalogo__produto=produto,
            catalogo__ativo=True,
            codigo=codigo,
        ).values_list('ativa', flat=True).first()
        if configuracao is not None:
            return configuracao
        return codigo in CapacidadeCatalogoProdutoEmpresa.CAPACIDADES_LEGADAS_ATIVAS

    @classmethod
    def produtos_habilitados(cls, *, empresa, codigo, produtos=None):
        produtos = produtos if produtos is not None else CatalogoProdutoEmpresa.objects.filter(
            empresa=empresa,
            ativo=True,
        ).values_list('produto_id', flat=True)
        produto_ids = set(
            produtos.values_list('pk', flat=True)
            if (
                hasattr(produtos, 'model')
                and produtos.model._meta.label_lower == 'estoque.produto'
            )
            else produtos
        )
        configuracoes = dict(
            CapacidadeCatalogoProdutoEmpresa.objects.filter(
                catalogo__empresa=empresa,
                catalogo__produto_id__in=produto_ids,
                catalogo__ativo=True,
                codigo=codigo,
            ).values_list('catalogo__produto_id', 'ativa')
        )
        padrao = codigo in CapacidadeCatalogoProdutoEmpresa.CAPACIDADES_LEGADAS_ATIVAS
        return {
            produto_id for produto_id in produto_ids
            if configuracoes.get(produto_id, padrao)
        }
