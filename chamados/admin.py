from django.contrib import admin

from chamados.models import CategoriaChamado, Chamado, ChamadoAnexo, ChamadoEvento, ChamadoMensagem


@admin.register(CategoriaChamado)
class CategoriaChamadoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'sla_horas', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome', 'descricao')


class ChamadoMensagemInline(admin.TabularInline):
    model = ChamadoMensagem
    extra = 0
    readonly_fields = ('autor', 'texto', 'nota_interna', 'criado_em')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    list_display = ('protocolo', 'titulo', 'base', 'prioridade', 'status', 'atendente', 'aberto_em')
    list_filter = ('status', 'prioridade', 'categoria', 'base')
    search_fields = ('protocolo', 'titulo', 'descricao', 'loja', 'lider')
    inlines = (ChamadoMensagemInline,)

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ChamadoAnexo)
class ChamadoAnexoAdmin(admin.ModelAdmin):
    list_display = ('chamado', 'nome_original', 'enviado_por', 'criado_em')
    readonly_fields = ('chamado', 'mensagem', 'arquivo', 'nome_original', 'enviado_por', 'criado_em')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ChamadoEvento)
class ChamadoEventoAdmin(admin.ModelAdmin):
    list_display = ('chamado', 'tipo', 'usuario', 'criado_em')
    readonly_fields = ('chamado', 'tipo', 'descricao', 'dados', 'usuario', 'criado_em')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
