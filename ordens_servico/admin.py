from django.contrib import admin

from ordens_servico.models import (
    OrdemServico,
    OrdemServicoAnexo,
    OrdemServicoAssinatura,
    OrdemServicoEvento,
    OrdemServicoLinha,
)


class LinhaInline(admin.TabularInline):
    model = OrdemServicoLinha
    extra = 0
    readonly_fields = [field.name for field in OrdemServicoLinha._meta.fields]
    can_delete = False


@admin.register(OrdemServico)
class OrdemServicoAdmin(admin.ModelAdmin):
    list_display = ('numero', 'tipo', 'empresa', 'status', 'prioridade', 'aberto_em')
    list_filter = ('tipo', 'status', 'prioridade', 'empresa')
    search_fields = ('numero', 'motivo', 'descricao')
    inlines = [LinhaInline]


admin.site.register(OrdemServicoAssinatura)
admin.site.register(OrdemServicoEvento)
admin.site.register(OrdemServicoAnexo)
