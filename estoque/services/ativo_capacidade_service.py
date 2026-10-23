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

    @classmethod
    def identificadores(cls, *, empresa, produto):
        """Retorna as regras de identificação do produto no tenant."""
        capacidade = CapacidadeCatalogoProdutoEmpresa
        possui_patrimonio = cls.habilitada(
            empresa=empresa,
            produto=produto,
            codigo=capacidade.POSSUI_PATRIMONIO,
        )
        possui_serie = cls.habilitada(
            empresa=empresa,
            produto=produto,
            codigo=capacidade.POSSUI_SERIE,
        )
        possui_imei = cls.habilitada(
            empresa=empresa,
            produto=produto,
            codigo=capacidade.POSSUI_IMEI,
        )
        return {
            'possui_patrimonio': possui_patrimonio,
            'patrimonio_obrigatorio': possui_patrimonio and cls.habilitada(
                empresa=empresa,
                produto=produto,
                codigo=capacidade.PATRIMONIO_OBRIGATORIO,
            ),
            'possui_serie': possui_serie,
            'serie_obrigatoria': possui_serie and cls.habilitada(
                empresa=empresa,
                produto=produto,
                codigo=capacidade.SERIE_OBRIGATORIA,
            ),
            'possui_imei': possui_imei,
            'imei_obrigatorio': False,
        }

    @classmethod
    def validar_identificadores(
        cls,
        *,
        empresa,
        produto,
        numero_serie='',
        patrimonio='',
    ):
        """Normaliza e valida identificadores sem consultar unicidade."""
        regras = cls.identificadores(empresa=empresa, produto=produto)
        serie = (numero_serie or '').strip().upper() or None
        patrimonio_normalizado = (patrimonio or '').strip().upper() or None
        erros = {}

        if regras['serie_obrigatoria'] and not serie:
            erros['numero_serie'] = 'Informe o número de série deste ativo.'
        elif not regras['possui_serie'] and serie:
            erros['numero_serie'] = (
                'O produto selecionado não utiliza número de série.'
            )

        if regras['patrimonio_obrigatorio'] and not patrimonio_normalizado:
            erros['patrimonio'] = 'Informe o patrimônio deste ativo.'
        elif not regras['possui_patrimonio'] and patrimonio_normalizado:
            erros['patrimonio'] = (
                'O produto selecionado não utiliza patrimônio.'
            )

        return serie, patrimonio_normalizado, regras, erros
