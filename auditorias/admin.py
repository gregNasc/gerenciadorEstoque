from django.contrib import admin

from .models import (
    AuditoriaBase,
    AuditoriaDivergencia,
    AuditoriaEvento,
    AuditoriaLeitura,
    AuditoriaResolucao,
    AuditoriaSnapshotEquipamento,
    CampanhaAuditoria,
    CampanhaAuditoriaEvento,
)


class AuditoriaSomenteLeituraAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


@admin.register(CampanhaAuditoria)
class CampanhaAuditoriaAdmin(AuditoriaSomenteLeituraAdmin):
    list_display = ('nome', 'empresa', 'status', 'criado_em')
    list_filter = ('status', 'empresa')


@admin.register(AuditoriaBase)
class AuditoriaBaseAdmin(AuditoriaSomenteLeituraAdmin):
    list_display = ('campanha', 'base', 'inicio_em', 'fim_em', 'status')
    list_filter = ('status', 'campanha__empresa')


admin.site.register(AuditoriaSnapshotEquipamento, AuditoriaSomenteLeituraAdmin)
admin.site.register(AuditoriaLeitura, AuditoriaSomenteLeituraAdmin)
admin.site.register(AuditoriaDivergencia, AuditoriaSomenteLeituraAdmin)
admin.site.register(AuditoriaResolucao, AuditoriaSomenteLeituraAdmin)
admin.site.register(AuditoriaEvento, AuditoriaSomenteLeituraAdmin)
admin.site.register(CampanhaAuditoriaEvento, AuditoriaSomenteLeituraAdmin)
