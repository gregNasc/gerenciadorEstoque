from django.contrib import admin

from compras.models import (
    Aquisicao,
    CatalogoProdutoEmpresa,
    FornecedorEmpresa,
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


@admin.register(FornecedorEmpresa)
class FornecedorEmpresaAdmin(admin.ModelAdmin):
    list_display = (
        'empresa', 'fornecedor', 'status', 'codigo_interno', 'homologado_em',
    )
    list_filter = ('status', 'empresa')
    search_fields = (
        'empresa__nome', 'fornecedor__nome', 'fornecedor__documento',
        'codigo_interno',
    )

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
