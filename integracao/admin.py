from django.contrib import admin

from integracao.models import (
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
