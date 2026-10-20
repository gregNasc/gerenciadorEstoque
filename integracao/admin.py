from django.contrib import admin

from integracao.models import (
    CaepiImportacao,
    CaepiRegistro,
    DocusignEnvelope,
    DocusignEvent,
    DocusignTenantConfig,
    InventoryPlanningEventBinding,
    InventoryPlanningSyncRun,
    PlanningClient,
    PlanningClientBinding,
    PlanningEvent,
    PlanningInventoryType,
    PlanningOperationalBaseBinding,
    PlanningRegion,
    PlanningRegionBinding,
    PlanningStore,
)


@admin.register(CaepiImportacao)
class CaepiImportacaoAdmin(admin.ModelAdmin):
    list_display = ('nome_arquivo', 'status', 'total_registros', 'criado_por', 'criado_em', 'publicado_em')
    list_filter = ('status',)
    search_fields = ('nome_arquivo', 'sha256')
    readonly_fields = [field.name for field in CaepiImportacao._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CaepiRegistro)
class CaepiRegistroAdmin(admin.ModelAdmin):
    list_display = ('numero_ca', 'situacao', 'validade_ca', 'natureza', 'equipamento', 'importacao')
    list_filter = ('situacao', 'natureza')
    search_fields = ('numero_ca', 'equipamento', 'descricao_equipamento', 'marca', 'referencia')
    readonly_fields = [field.name for field in CaepiRegistro._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DocusignTenantConfig)
class DocusignTenantConfigAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'habilitada', 'email_testemunha_rh', 'atualizado_em')
    list_filter = ('habilitada',)
    search_fields = ('empresa__nome', 'email_testemunha_rh')


@admin.register(DocusignEnvelope)
class DocusignEnvelopeAdmin(admin.ModelAdmin):
    list_display = (
        'envelope_id', 'empresa', 'tipo_documento', 'status', 'enviado_em',
        'concluido_em',
    )
    list_filter = ('status', 'tipo_documento', 'empresa')
    search_fields = ('envelope_id', 'idempotency_key', 'empresa__nome')
    readonly_fields = [field.name for field in DocusignEnvelope._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DocusignEvent)
class DocusignEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'status', 'envelope', 'ocorrido_em', 'recebido_em')
    list_filter = ('event_type', 'status')
    search_fields = ('envelope__envelope_id', 'event_key')
    readonly_fields = [field.name for field in DocusignEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PlanningRegion, PlanningClient, PlanningStore, PlanningInventoryType)
class PlanningCatalogAdmin(admin.ModelAdmin):
    list_display = ("external_id", "data_source", "sync_state", "synced_at")
    search_fields = ("external_id",)
    list_filter = ("sync_state", "data_source")
    readonly_fields = (
        "external_id",
        "data_source",
        "synced_at",
        "last_seen_at",
        "external_created_at",
        "external_updated_at",
    )

@admin.register(PlanningEvent)
class PlanningEventAdmin(admin.ModelAdmin):
    list_display = (
        "external_id",
        "status",
        "planned_at",
        "inventory_type",
        "materialization_status",
        "sync_state",
    )
    list_filter = ("status", "materialization_status", "sync_state")
    search_fields = ("external_id", "import_key", "store__code", "store__name")
    readonly_fields = [field.name for field in PlanningEvent._meta.fields]

@admin.register(
    PlanningClientBinding,
    PlanningRegionBinding,
    PlanningOperationalBaseBinding,
)
class PlanningBindingAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "source",
        "is_active",
        "confirmed_at",
        "confirmed_by",
    )
    list_filter = ("source", "is_active")
    readonly_fields = ("confirmed_at",)

@admin.register(InventoryPlanningEventBinding)
class EventBindingAdmin(admin.ModelAdmin):
    list_display = ("planning_event", "inventory", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")

@admin.register(InventoryPlanningSyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    list_display = (
        "endpoint",
        "status",
        "started_at",
        "finished_at",
        "received",
        "created",
        "updated",
        "missing",
    )
    list_filter = ("status", "endpoint")
    readonly_fields = [field.name for field in InventoryPlanningSyncRun._meta.fields]
