from django.contrib import admin

from compras.models import (
    Aquisicao,
    CatalogoProdutoEmpresa,
    ItemAquisicao,
    RemessaCompra,
)


class ItemAquisicaoInline(admin.TabularInline):
    model = ItemAquisicao
    extra = 0


@admin.register(Aquisicao)
class AquisicaoAdmin(admin.ModelAdmin):
    list_display = ('id', 'empresa', 'fornecedor', 'numero_documento', 'data_compra', 'status')
    list_filter = ('status', 'empresa')
    search_fields = ('numero_documento', 'chave_nfe', 'numero_pedido_compra')
    inlines = [ItemAquisicaoInline]


@admin.register(RemessaCompra)
class RemessaCompraAdmin(admin.ModelAdmin):
    list_display = ('protocolo', 'fluxo', 'base_destino', 'status', 'criada_em')
    list_filter = ('fluxo', 'status')
    search_fields = ('protocolo', 'codigo_rastreio')


@admin.register(CatalogoProdutoEmpresa)
class CatalogoProdutoEmpresaAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'produto', 'ativo', 'configurado_por', 'atualizado_em')
    list_filter = ('ativo', 'empresa', 'produto__categoria')
    search_fields = ('empresa__nome', 'produto__descricao', 'produto__codigo')
