from django.conf import settings
from django.db import models
from django.db.models import Q

from integracao.constants import DATA_SOURCE_INVENTORY_PLANNING


class SyncState(models.TextChoices):
    PRESENT = "PRESENT", "Presente"
    MISSING = "MISSING", "Ausente na fonte"


class ExternalSyncModel(models.Model):
    external_id = models.CharField(max_length=128)
    data_source = models.CharField(
        max_length=40,
        default=DATA_SOURCE_INVENTORY_PLANNING,
        editable=False,
    )
    synced_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    external_created_at = models.DateTimeField(null=True, blank=True)
    external_updated_at = models.DateTimeField(null=True, blank=True)
    sync_state = models.CharField(
        max_length=16,
        choices=SyncState.choices,
        default=SyncState.PRESENT,
        db_index=True,
    )

    class Meta:
        abstract = True


class PlanningRegion(ExternalSyncModel):
    name = models.CharField(max_length=160)
    state = models.CharField(max_length=2, blank=True, default="")
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("data_source", "external_id"),
                name="uniq_plan_region_source_id",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.external_id})"


class PlanningClient(ExternalSyncModel):
    corporate_name = models.CharField(max_length=255, blank=True, default="")
    trade_name = models.CharField(max_length=255, blank=True, default="")
    code = models.CharField(max_length=80, blank=True, default="")
    segment_external_id = models.CharField(max_length=128, blank=True, default="")
    segment_name = models.CharField(max_length=160, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("trade_name", "corporate_name")
        constraints = [
            models.UniqueConstraint(
                fields=("data_source", "external_id"),
                name="uniq_plan_client_source_id",
            )
        ]

    def __str__(self):
        return self.trade_name or self.corporate_name or self.external_id


class PlanningStore(ExternalSyncModel):
    client = models.ForeignKey(
        PlanningClient,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stores",
    )
    region = models.ForeignKey(
        PlanningRegion,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="stores",
    )
    code = models.CharField(max_length=100, blank=True, default="")
    store_number = models.CharField(max_length=80, blank=True, default="")
    name = models.CharField(max_length=255, blank=True, default="")
    nickname = models.CharField(max_length=255, blank=True, default="")
    corporate_document = models.CharField(max_length=32, blank=True, default="")
    address = models.CharField(max_length=255, blank=True, default="")
    district = models.CharField(max_length=120, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    state = models.CharField(max_length=2, blank=True, default="")
    zip_code = models.CharField(max_length=20, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("data_source", "external_id"),
                name="uniq_plan_store_source_id",
            )
        ]
        indexes = [
            models.Index(fields=("client", "code"), name="plan_store_client_code"),
            models.Index(fields=("region", "store_number"), name="plan_store_region_num"),
        ]

    def __str__(self):
        return self.code or self.name or self.external_id


class PlanningInventoryType(ExternalSyncModel):
    class Kind(models.TextChoices):
        PARENT = "PAI", "PAI"
        CHILD = "FILHO", "FILHO"

    name = models.CharField(max_length=180)
    code = models.CharField(max_length=80, blank=True, default="")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("kind", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("data_source", "external_id"),
                name="uniq_plan_type_source_id",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.kind})"


class PlanningEvent(ExternalSyncModel):
    class MaterializationStatus(models.TextChoices):
        PENDING = "PENDING", "Pendente de vínculos"
        MATERIALIZED = "MATERIALIZED", "Inventário criado"
        NOT_APPLICABLE = "NOT_APPLICABLE", "Evento FILHO"
        ERROR = "ERROR", "Erro de materialização"

    status = models.CharField(max_length=24, db_index=True)
    planned_at = models.DateTimeField(db_index=True)
    planned_pieces = models.PositiveBigIntegerField(null=True, blank=True)
    planned_headcount = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    parent_external_id = models.CharField(max_length=128, blank=True, default="")
    store = models.ForeignKey(
        PlanningStore,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="events",
    )
    client = models.ForeignKey(
        PlanningClient,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="events",
    )
    region = models.ForeignKey(
        PlanningRegion,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="events",
    )
    inventory_type = models.ForeignKey(
        PlanningInventoryType,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="events",
    )
    import_data = models.JSONField(default=dict, blank=True)
    import_key = models.CharField(max_length=255, blank=True, default="")
    import_revision = models.CharField(max_length=120, blank=True, default="")
    metrics = models.JSONField(default=list, blank=True)
    meeting_point_external_id = models.CharField(max_length=128, blank=True, default="")
    meeting_point_name = models.CharField(max_length=255, blank=True, default="")
    sensitive_data_filtered = models.BooleanField(default=False)
    source_payload_hash = models.CharField(max_length=64, blank=True, default="")
    materialization_status = models.CharField(
        max_length=20,
        choices=MaterializationStatus.choices,
        default=MaterializationStatus.PENDING,
        db_index=True,
    )
    materialization_error = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ("planned_at", "external_id")
        constraints = [
            models.UniqueConstraint(
                fields=("data_source", "external_id"),
                name="uniq_plan_event_source_id",
            )
        ]
        indexes = [
            models.Index(fields=("planned_at", "status"), name="plan_event_date_status"),
            models.Index(fields=("region", "planned_at"), name="plan_event_region_date"),
            models.Index(fields=("parent", "planned_at"), name="plan_event_parent_date"),
        ]

    @property
    def is_parent(self):
        return bool(
            self.inventory_type_id
            and self.inventory_type.kind == PlanningInventoryType.Kind.PARENT
            and not self.parent_external_id
        )

    def __str__(self):
        return f"{self.external_id} - {self.planned_at:%Y-%m-%d %H:%M}"


class PlanningClientBinding(models.Model):
    planning_client = models.OneToOneField(
        PlanningClient,
        on_delete=models.CASCADE,
        related_name="local_binding",
    )
    local_client = models.OneToOneField(
        "insumos.Cliente",
        on_delete=models.PROTECT,
        related_name="planning_binding",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="planning_client_bindings_confirmed",
    )
    confirmed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.planning_client} → {self.local_client}"


class PlanningRegionBinding(models.Model):
    planning_region = models.OneToOneField(
        PlanningRegion,
        on_delete=models.CASCADE,
        related_name="local_binding",
    )
    local_base = models.ForeignKey(
        "estoque.Base",
        on_delete=models.PROTECT,
        related_name="planning_region_bindings",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="planning_region_bindings_confirmed",
    )
    confirmed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.planning_region} → {self.local_base}"


class InventoryPlanningEventBinding(models.Model):
    planning_event = models.OneToOneField(
        PlanningEvent,
        on_delete=models.CASCADE,
        related_name="inventory_binding",
    )
    inventory = models.OneToOneField(
        "insumos.Inventario",
        on_delete=models.PROTECT,
        related_name="planning_event_binding",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.planning_event.external_id} → Inventário #{self.inventory_id}"


class InventoryPlanningSyncRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Executando"
        SUCCESS = "SUCCESS", "Sucesso"
        FAILED = "FAILED", "Falha"

    endpoint = models.CharField(max_length=80)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    scope = models.JSONField(default=dict, blank=True)
    pages = models.PositiveIntegerField(default=0)
    received = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    updated = models.PositiveIntegerField(default=0)
    missing = models.PositiveIntegerField(default=0)
    materialized = models.PositiveIntegerField(default=0)
    pending_materialization = models.PositiveIntegerField(default=0)
    rate_limit_limit = models.PositiveIntegerField(null=True, blank=True)
    rate_limit_remaining = models.PositiveIntegerField(null=True, blank=True)
    rate_limit_reset = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True, default="")
    error_message = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ("-started_at",)
        indexes = [
            models.Index(fields=("endpoint", "started_at"), name="plan_sync_endpoint_date"),
            models.Index(fields=("status", "started_at"), name="plan_sync_status_date"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("endpoint",),
                condition=Q(status="RUNNING"),
                name="uniq_running_plan_sync_endpoint",
            )
        ]

    def __str__(self):
        return f"{self.endpoint} - {self.status} - {self.started_at:%Y-%m-%d %H:%M}"
