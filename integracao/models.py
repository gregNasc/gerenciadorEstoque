from pathlib import Path
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import storages
from django.db import models
from django.db.models import Q
from django.utils import timezone

from integracao.constants import DATA_SOURCE_INVENTORY_PLANNING


def docusign_signed_document_storage():
    return storages['private']


def docusign_signed_document_upload_to(instance, filename):
    extension = Path(filename).suffix.lower() or '.pdf'
    return (
        f'custodias/{instance.empresa_id}/docusign/assinados/'
        f'{uuid.uuid4().hex}{extension}'
    )


def docusign_certificate_upload_to(instance, filename):
    extension = Path(filename).suffix.lower() or '.pdf'
    return (
        f'custodias/{instance.empresa_id}/docusign/certificados/'
        f'{uuid.uuid4().hex}{extension}'
    )


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
        SKIPPED = "SKIPPED", "Não criado pelo status externo"
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

class BindingSource(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    SUGGESTED = "SUGGESTED", "Sugerido"
    RULE = "RULE", "Regra confirmada"

class PlanningClientBinding(models.Model):
    planning_client = models.OneToOneField(
        PlanningClient,
        on_delete=models.CASCADE,
        related_name="local_binding",
    )
    local_client = models.ForeignKey(
        "insumos.Cliente",
        on_delete=models.PROTECT,
        related_name="planning_bindings",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="planning_client_bindings_confirmed",
    )
    confirmed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    source = models.CharField(
        max_length=20,
        choices=BindingSource.choices,
        default=BindingSource.MANUAL,
    )
    is_active = models.BooleanField(default=True)

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
    updated_at = models.DateTimeField(auto_now=True)
    source = models.CharField(
        max_length=20,
        choices=BindingSource.choices,
        default=BindingSource.MANUAL,
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.planning_region} → {self.local_base}"

class PlanningOperationalBaseBinding(models.Model):
    planning_client = models.ForeignKey(
        PlanningClient,
        on_delete=models.CASCADE,
        related_name="operational_base_bindings",
    )
    planning_region = models.ForeignKey(
        PlanningRegion,
        on_delete=models.CASCADE,
        related_name="operational_base_bindings",
    )
    local_base = models.ForeignKey(
        "estoque.Base",
        on_delete=models.PROTECT,
        related_name="planning_operational_bindings",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="planning_operational_bindings_confirmed",
    )
    confirmed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    source = models.CharField(
        max_length=20,
        choices=BindingSource.choices,
        default=BindingSource.MANUAL,
    )
    reason = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("planning_client", "planning_region"),
                name="uniq_planning_client_region_binding",
            )
        ]
        indexes = [
            models.Index(
                fields=("local_base", "is_active"),
                name="plan_op_base_active",
            )
        ]
        permissions = [
            ("gerenciar_mapeamentos_planning", "Pode gerenciar mapeamentos do planejamento"),
            ("executar_materializacao_planning", "Pode executar materialização do planejamento"),
        ]

    def __str__(self):
        return (
            f"{self.planning_client} + {self.planning_region} "
            f"→ {self.local_base}"
        )

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
        STALE = "STALE", "Abandonada"

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


class DocusignTenantConfig(models.Model):
    empresa = models.OneToOneField(
        'estoque.Empresa',
        on_delete=models.CASCADE,
        related_name='configuracao_docusign',
    )
    habilitada = models.BooleanField(default=False, db_index=True)
    conta_id = models.CharField(
        'ID da conta DocuSign',
        max_length=100,
        blank=True,
        default='',
        help_text='Opcional; quando vazio, usa DOCUSIGN_ACCOUNT_ID do ambiente.',
    )
    nome_testemunha_rh = models.CharField(
        max_length=200,
        default='SETOR DE RH',
    )
    email_testemunha_rh = models.EmailField(blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração DocuSign por empresa'
        verbose_name_plural = 'Configurações DocuSign por empresa'
        ordering = ('empresa__nome',)

    def clean(self):
        super().clean()
        if self.habilitada and not self.email_testemunha_rh:
            raise ValidationError({
                'email_testemunha_rh': (
                    'Informe o e-mail do RH antes de habilitar o DocuSign.'
                ),
            })

    def save(self, *args, **kwargs):
        self.conta_id = (self.conta_id or '').strip()
        self.nome_testemunha_rh = (
            self.nome_testemunha_rh or 'SETOR DE RH'
        ).strip()
        self.email_testemunha_rh = (
            self.email_testemunha_rh or ''
        ).strip().lower()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'DocuSign — {self.empresa}'


class DocusignEnvelope(models.Model):
    class TipoDocumento(models.TextChoices):
        ENTREGA = 'ENTREGA', 'Termo de Entrega'
        DEVOLUCAO = 'DEVOLUCAO', 'Termo de Devolução'

    class Status(models.TextChoices):
        PREPARANDO = 'PREPARANDO', 'Preparando'
        ENVIADO = 'ENVIADO', 'Enviado'
        ENTREGUE = 'ENTREGUE', 'Entregue aos destinatários'
        ASSINADO = 'ASSINADO', 'Assinado parcialmente'
        CONCLUIDO = 'CONCLUIDO', 'Concluído'
        RECUSADO = 'RECUSADO', 'Recusado'
        ANULADO = 'ANULADO', 'Anulado'
        ERRO = 'ERRO', 'Erro'

    provider = models.CharField(max_length=30, default='DOCUSIGN', editable=False)
    empresa = models.ForeignKey(
        'estoque.Empresa',
        on_delete=models.PROTECT,
        related_name='envelopes_docusign',
    )
    custodia = models.ForeignKey(
        'estoque.Custodia',
        on_delete=models.PROTECT,
        related_name='envelopes_docusign',
    )
    termo_entrega = models.ForeignKey(
        'estoque.TermoEntregaCustodia',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='envelopes_docusign',
    )
    termo_devolucao = models.ForeignKey(
        'estoque.TermoDevolucaoCustodia',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='envelopes_docusign',
    )
    tipo_documento = models.CharField(max_length=12, choices=TipoDocumento.choices)
    idempotency_key = models.CharField(max_length=120, unique=True, editable=False)
    envelope_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PREPARANDO,
        db_index=True,
    )
    participantes = models.JSONField(default=list, editable=False)
    provider_metadata = models.JSONField(default=dict, blank=True, editable=False)
    pdf_assinado = models.FileField(
        storage=docusign_signed_document_storage,
        upload_to=docusign_signed_document_upload_to,
        null=True,
        blank=True,
        editable=False,
    )
    pdf_assinado_sha256 = models.CharField(
        max_length=64, blank=True, default='', editable=False,
    )
    certificado = models.FileField(
        storage=docusign_signed_document_storage,
        upload_to=docusign_certificate_upload_to,
        null=True,
        blank=True,
        editable=False,
    )
    certificado_sha256 = models.CharField(
        max_length=64, blank=True, default='', editable=False,
    )
    enviado_em = models.DateTimeField(null=True, blank=True)
    assinado_em = models.DateTimeField(null=True, blank=True)
    concluido_em = models.DateTimeField(null=True, blank=True)
    ultima_falha = models.CharField(max_length=500, blank=True, default='')
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='envelopes_docusign_criados',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Envelope DocuSign'
        verbose_name_plural = 'Envelopes DocuSign'
        ordering = ('-criado_em', '-id')
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(termo_entrega__isnull=False, termo_devolucao__isnull=True)
                    | Q(termo_entrega__isnull=True, termo_devolucao__isnull=False)
                ),
                name='docusign_envelope_um_termo',
            ),
            models.UniqueConstraint(
                fields=('provider', 'envelope_id'),
                condition=~Q(envelope_id=''),
                name='docusign_provider_envelope_unico',
            ),
            models.UniqueConstraint(
                fields=('termo_entrega',),
                condition=Q(termo_entrega__isnull=False),
                name='docusign_termo_entrega_unico',
            ),
            models.UniqueConstraint(
                fields=('termo_devolucao',),
                condition=Q(termo_devolucao__isnull=False),
                name='docusign_termo_devolucao_unico',
            ),
        ]
        indexes = [
            models.Index(
                fields=('empresa', 'status', 'criado_em'),
                name='docusign_empresa_status_idx',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if bool(self.termo_entrega_id) == bool(self.termo_devolucao_id):
            errors['tipo_documento'] = 'Informe exatamente um termo.'
        term_empresa_id = None
        term_custodia_id = None
        expected_type = None
        if self.termo_entrega_id:
            term_empresa_id = self.termo_entrega.custodia.empresa_id
            term_custodia_id = self.termo_entrega.custodia_id
            expected_type = self.TipoDocumento.ENTREGA
        elif self.termo_devolucao_id:
            term_empresa_id = self.termo_devolucao.devolucao.custodia.empresa_id
            term_custodia_id = self.termo_devolucao.devolucao.custodia_id
            expected_type = self.TipoDocumento.DEVOLUCAO
        if term_empresa_id and self.empresa_id != term_empresa_id:
            errors['empresa'] = 'A empresa deve ser a mesma do termo.'
        if term_custodia_id and self.custodia_id != term_custodia_id:
            errors['custodia'] = 'A Custódia deve ser a mesma do termo.'
        if expected_type and self.tipo_documento != expected_type:
            errors['tipo_documento'] = 'O tipo não corresponde ao termo informado.'
        if self.criado_por_id and not self.criado_por.is_active:
            errors['criado_por'] = 'O usuário responsável deve estar ativo.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.envelope_id = (self.envelope_id or '').strip()
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def termo(self):
        return self.termo_entrega or self.termo_devolucao

    def __str__(self):
        return f'DocuSign {self.envelope_id or self.idempotency_key} — {self.status}'


class DocusignEvent(models.Model):
    envelope = models.ForeignKey(
        DocusignEnvelope,
        on_delete=models.CASCADE,
        related_name='eventos',
    )
    event_key = models.CharField(max_length=64, unique=True, editable=False)
    event_type = models.CharField(max_length=120)
    status = models.CharField(max_length=60, blank=True, default='')
    ocorrido_em = models.DateTimeField(null=True, blank=True)
    recebido_em = models.DateTimeField(auto_now_add=True)
    payload_sha256 = models.CharField(max_length=64, editable=False)
    payload = models.JSONField(default=dict, editable=False)

    class Meta:
        verbose_name = 'Evento DocuSign'
        verbose_name_plural = 'Eventos DocuSign'
        ordering = ('recebido_em', 'id')
        indexes = [
            models.Index(
                fields=('envelope', 'recebido_em'),
                name='docusign_event_envelope_idx',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Eventos DocuSign são imutáveis.')
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.event_type} — {self.envelope}'


class CaepiImportacao(models.Model):
    class Status(models.TextChoices):
        PROCESSANDO = 'PROCESSANDO', 'Processando'
        PREVIA = 'PREVIA', 'Prévia pronta'
        PUBLICADA = 'PUBLICADA', 'Publicada'
        SUBSTITUIDA = 'SUBSTITUIDA', 'Substituída'
        FALHOU = 'FALHOU', 'Falhou'
        INTERROMPIDA = 'INTERROMPIDA', 'Interrompida'

    nome_arquivo = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, unique=True, db_index=True)
    tamanho_bytes = models.PositiveBigIntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PROCESSANDO,
        db_index=True,
    )
    total_registros = models.PositiveIntegerField(default=0)
    processados = models.PositiveBigIntegerField(default=0)
    novos = models.PositiveIntegerField(default=0)
    alterados = models.PositiveIntegerField(default=0)
    inalterados = models.PositiveIntegerField(default=0)
    rejeitados = models.PositiveIntegerField(default=0)
    advertencias = models.JSONField(default=list, blank=True)
    erro = models.TextField(blank=True, default='')
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name='importacoes_caepi',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True, db_index=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    publicado_em = models.DateTimeField(null=True, blank=True)
    duracao_ms = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ('-criado_em',)
        verbose_name = 'Importação CAEPI'
        verbose_name_plural = 'Importações CAEPI'
        constraints = [
            models.UniqueConstraint(
                fields=('status',),
                condition=Q(status='PUBLICADA'),
                name='caepi_uma_importacao_publicada',
            ),
        ]

    def __str__(self):
        return f'{self.nome_arquivo} — {self.get_status_display()}'

    @property
    def esta_interrompida(self):
        from datetime import timedelta

        return (
            self.status == self.Status.INTERROMPIDA
            or (
                self.status == self.Status.PROCESSANDO
                and self.atualizado_em <= timezone.now() - timedelta(minutes=10)
            )
        )

    @property
    def status_exibicao(self):
        return 'Interrompida' if self.esta_interrompida else self.get_status_display()


class CaepiRegistro(models.Model):
    importacao = models.ForeignKey(
        CaepiImportacao,
        on_delete=models.CASCADE,
        related_name='registros',
    )
    numero_ca = models.CharField(max_length=40, db_index=True)
    validade_ca = models.DateField(null=True, blank=True, db_index=True)
    situacao = models.CharField(max_length=80, blank=True, default='', db_index=True)
    natureza = models.CharField(max_length=80, blank=True, default='')
    equipamento = models.CharField(max_length=255, blank=True, default='')
    descricao_equipamento = models.TextField(blank=True, default='')
    marca = models.CharField(max_length=255, blank=True, default='')
    referencia = models.CharField(max_length=255, blank=True, default='')
    cor = models.CharField(max_length=255, blank=True, default='')
    aprovado_para = models.TextField(blank=True, default='')
    restricao = models.TextField(blank=True, default='')
    observacao_analise = models.TextField(blank=True, default='')
    numero_laudo = models.CharField(max_length=255, blank=True, default='')
    norma = models.TextField(blank=True, default='')
    hash_registro = models.CharField(max_length=64, db_index=True)

    class Meta:
        ordering = ('numero_ca', 'id')
        verbose_name = 'Registro CAEPI'
        verbose_name_plural = 'Registros CAEPI'
        constraints = [
            models.UniqueConstraint(
                fields=('importacao', 'hash_registro'),
                name='caepi_registro_hash_importacao_uq',
            ),
        ]
        indexes = [
            models.Index(
                fields=('importacao', 'numero_ca'),
                name='caepi_import_ca_idx',
            ),
        ]

    def __str__(self):
        return f'CA {self.numero_ca} — {self.equipamento or self.descricao_equipamento}'
