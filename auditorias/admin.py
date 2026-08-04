from django.contrib import admin

from .models import (
    AuditoriaBase,
    AuditoriaDivergencia,
    AuditoriaEvento,
    AuditoriaLeitura,
    AuditoriaResolucao,
    AuditoriaSnapshotEquipamento,
    CampanhaAuditoria,
)


@admin.register(CampanhaAuditoria)
class CampanhaAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'empresa', 'status', 'criado_em')
    list_filter = ('status', 'empresa')


@admin.register(AuditoriaBase)
class AuditoriaBaseAdmin(admin.ModelAdmin):
    list_display = ('campanha', 'base', 'inicio_em', 'fim_em', 'status')
    list_filter = ('status', 'campanha__empresa')


admin.site.register(AuditoriaSnapshotEquipamento)
admin.site.register(AuditoriaLeitura)
admin.site.register(AuditoriaDivergencia)
admin.site.register(AuditoriaResolucao)
admin.site.register(AuditoriaEvento)
