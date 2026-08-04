import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from estoque.models import Base, Empresa, Equipamento, Transferencia


class CampanhaAuditoria(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = 'RASCUNHO', _('Rascunho')
        AGENDADA = 'AGENDADA', _('Agendada')
        EM_ANDAMENTO = 'EM_ANDAMENTO', _('Em andamento')
        ENCERRADA = 'ENCERRADA', _('Encerrada')
        CANCELADA = 'CANCELADA', _('Cancelada')

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name='campanhas_auditoria')
    nome = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)
    instrucoes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO, db_index=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='campanhas_auditoria_criadas',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    encerrado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return self.nome


class AuditoriaBase(models.Model):
    class Status(models.TextChoices):
        NAO_INICIADA = 'NAO_INICIADA', _('Não iniciada')
        DISPONIVEL = 'DISPONIVEL', _('Disponível')
        EM_ANDAMENTO = 'EM_ANDAMENTO', _('Em andamento')
        ENVIADA = 'ENVIADA', _('Enviada para análise')
        COM_DIVERGENCIAS = 'COM_DIVERGENCIAS', _('Com divergências')
        EM_REGULARIZACAO = 'EM_REGULARIZACAO', _('Em regularização')
        FINALIZADA = 'FINALIZADA', _('Finalizada')
        REABERTA = 'REABERTA', _('Reaberta')
        EXPIRADA = 'EXPIRADA', _('Expirada')
        DISPENSADA = 'DISPENSADA', _('Dispensada')

    campanha = models.ForeignKey(CampanhaAuditoria, on_delete=models.CASCADE, related_name='auditorias_bases')
    base = models.ForeignKey(Base, on_delete=models.PROTECT, related_name='auditorias')
    inicio_em = models.DateTimeField()
    fim_em = models.DateTimeField()
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.NAO_INICIADA, db_index=True)
    snapshot_criado_em = models.DateTimeField(null=True, blank=True)
    iniciada_em = models.DateTimeField(null=True, blank=True)
    iniciada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='auditorias_iniciadas',
    )
    enviada_em = models.DateTimeField(null=True, blank=True)
    enviada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='auditorias_enviadas',
    )
    finalizada_em = models.DateTimeField(null=True, blank=True)
    finalizada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='auditorias_finalizadas',
    )
    correcao_solicitada_em = models.DateTimeField(null=True, blank=True)
    correcao_solicitada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='correcoes_auditoria_solicitadas',
    )
    prazo_correcao_em = models.DateTimeField(null=True, blank=True)
    orientacoes_correcao = models.TextField(blank=True)
    observacoes = models.TextField(blank=True)
    versao_reabertura = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['campanha', 'base'], name='uq_auditoria_campanha_base'),
        ]
        indexes = [models.Index(fields=['status', 'inicio_em', 'fim_em'])]

    def clean(self):
        super().clean()
        erros = {}
        if self.inicio_em and self.fim_em:
            if self.fim_em <= self.inicio_em:
                erros['fim_em'] = _('O encerramento deve ser posterior ao início.')
            elif self.fim_em - self.inicio_em > timedelta(days=31):
                erros['fim_em'] = _('O período máximo da auditoria é de 31 dias.')
        if self.base_id and self.campanha_id and self.base.empresa_id != self.campanha.empresa_id:
            erros['base'] = _('A base deve pertencer à empresa da campanha.')
        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return f'{self.campanha} - {self.base}'


class AuditoriaSnapshotEquipamento(models.Model):
    auditoria_base = models.ForeignKey(AuditoriaBase, on_delete=models.CASCADE, related_name='snapshot_equipamentos')
    equipamento = models.ForeignKey(Equipamento, on_delete=models.PROTECT, related_name='snapshots_auditoria')
    base_esperada = models.ForeignKey(Base, on_delete=models.PROTECT, related_name='+')
    produto_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)
    produto_descricao = models.CharField(max_length=255, blank=True)
    categoria = models.CharField(max_length=100, blank=True)
    codigo = models.CharField(max_length=100, blank=True)
    patrimonio = models.CharField(max_length=100, blank=True)
    numero_serie = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=50, blank=True)
    tipo_uso = models.CharField(max_length=30, blank=True)
    responsavel = models.CharField(max_length=150, blank=True)
    dados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['auditoria_base', 'equipamento'],
                name='uq_snapshot_auditoria_equipamento',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(_('O snapshot de auditoria é imutável.'))
        return super().save(*args, **kwargs)


class AuditoriaLeitura(models.Model):
    class Identificador(models.TextChoices):
        PATRIMONIO = 'PATRIMONIO', _('Patrimônio')
        SERIE = 'SERIE', _('Número de série')
        CODIGO = 'CODIGO', _('Código interno')
        DESCONHECIDO = 'DESCONHECIDO', _('Não identificado')

    class Origem(models.TextChoices):
        LEITOR = 'LEITOR', _('Leitor')
        MANUAL = 'MANUAL', _('Digitação manual')
        PLANILHA = 'PLANILHA', _('Importação de planilha')

    class Classificacao(models.TextChoices):
        CORRETO = 'CORRETO', _('Localizado na base correta')
        OUTRA_BASE = 'OUTRA_BASE', _('Localizado em outra base')
        NAO_CADASTRADO = 'NAO_CADASTRADO', _('Equipamento não cadastrado')
        IDENTIFICADOR_DUPLICADO = 'IDENTIFICADOR_DUPLICADO', _('Identificador duplicado')
        LEITURA_DUPLICADA = 'LEITURA_DUPLICADA', _('Leitura duplicada')
        EM_TRANSFERENCIA = 'EM_TRANSFERENCIA', _('Em transferência')
        EMPRESTADO = 'EMPRESTADO', _('Emprestado')
        STATUS_INCOMPATIVEL = 'STATUS_INCOMPATIVEL', _('Status incompatível')

    auditoria_base = models.ForeignKey(AuditoriaBase, on_delete=models.CASCADE, related_name='leituras')
    equipamento = models.ForeignKey(
        Equipamento, null=True, blank=True, on_delete=models.PROTECT,
        related_name='leituras_auditoria',
    )
    valor_informado = models.CharField(max_length=180, db_index=True)
    valor_normalizado = models.CharField(max_length=180, db_index=True)
    tipo_identificador = models.CharField(max_length=20, choices=Identificador.choices)
    origem = models.CharField(max_length=20, choices=Origem.choices, default=Origem.MANUAL)
    classificacao = models.CharField(max_length=30, choices=Classificacao.choices, db_index=True)
    base_encontrada = models.ForeignKey(Base, on_delete=models.PROTECT, related_name='+')
    lida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='leituras_auditoria')
    lida_em = models.DateTimeField(auto_now_add=True, db_index=True)
    cancelada = models.BooleanField(default=False, db_index=True)
    cancelada_em = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
    )
    motivo_cancelamento = models.TextField(blank=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True)
    dados_classificacao = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['auditoria_base', 'valor_normalizado']),
            models.Index(fields=['auditoria_base', 'equipamento', 'cancelada']),
        ]


class AuditoriaDivergencia(models.Model):
    class Tipo(models.TextChoices):
        OUTRA_BASE = 'OUTRA_BASE', _('Encontrado em outra base')
        NAO_LOCALIZADO = 'NAO_LOCALIZADO', _('Não localizado')
        NAO_CADASTRADO = 'NAO_CADASTRADO', _('Não cadastrado')
        IDENTIFICADOR_DUPLICADO = 'IDENTIFICADOR_DUPLICADO', _('Identificador duplicado')
        STATUS_INCOMPATIVEL = 'STATUS_INCOMPATIVEL', _('Status incompatível')
        CONFLITO_TRANSFERENCIA = 'CONFLITO_TRANSFERENCIA', _('Conflito com transferência')
        CONFLITO_EMPRESTIMO = 'CONFLITO_EMPRESTIMO', _('Conflito com empréstimo')

    class Status(models.TextChoices):
        ABERTA = 'ABERTA', _('Aberta')
        EM_ANALISE = 'EM_ANALISE', _('Em análise')
        AGUARDANDO_TRANSFERENCIA = 'AGUARDANDO_TRANSFERENCIA', _('Aguardando transferência')
        RESOLVIDA = 'RESOLVIDA', _('Resolvida')
        BLOQUEADA = 'BLOQUEADA', _('Bloqueada')
        CANCELADA = 'CANCELADA', _('Cancelada')

    auditoria_base = models.ForeignKey(AuditoriaBase, on_delete=models.CASCADE, related_name='divergencias')
    leitura = models.ForeignKey(
        AuditoriaLeitura, null=True, blank=True, on_delete=models.PROTECT, related_name='divergencias',
    )
    snapshot = models.ForeignKey(
        AuditoriaSnapshotEquipamento, null=True, blank=True,
        on_delete=models.PROTECT, related_name='divergencias',
    )
    equipamento = models.ForeignKey(
        Equipamento, null=True, blank=True, on_delete=models.PROTECT,
        related_name='divergencias_auditoria',
    )
    tipo = models.CharField(max_length=35, choices=Tipo.choices, db_index=True)
    status = models.CharField(max_length=35, choices=Status.choices, default=Status.ABERTA, db_index=True)
    base_esperada = models.ForeignKey(Base, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    base_encontrada = models.ForeignKey(Base, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    descricao = models.TextField(blank=True)
    motivo_bloqueio = models.TextField(blank=True)
    justificativa_base = models.TextField(blank=True)
    respondida_em = models.DateTimeField(null=True, blank=True)
    respondida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='divergencias_auditoria_respondidas',
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    resolvida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['auditoria_base', 'status', 'tipo'])]
        constraints = [
            models.UniqueConstraint(
                fields=['auditoria_base', 'snapshot', 'tipo'],
                condition=models.Q(snapshot__isnull=False),
                name='uq_divergencia_snapshot_tipo',
            ),
            models.UniqueConstraint(
                fields=['auditoria_base', 'leitura', 'tipo'],
                condition=models.Q(leitura__isnull=False),
                name='uq_divergencia_leitura_tipo',
            ),
        ]

    @property
    def identificador_informado(self):
        return self.leitura.valor_informado if self.leitura_id else ''

    @property
    def tipo_identificador_informado(self):
        return self.leitura.get_tipo_identificador_display() if self.leitura_id else ''


class AuditoriaResolucao(models.Model):
    class Tipo(models.TextChoices):
        MANTER_NA_BASE = 'MANTER_NA_BASE', _('Manter na base atual')
        TRANSFERIR = 'TRANSFERIR', _('Transferir equipamento')
        AJUSTE_ADMINISTRATIVO = 'AJUSTE_ADMINISTRATIVO', _('Ajuste administrativo')
        SEM_ACAO = 'SEM_ACAO', _('Sem alteração')

    divergencia = models.OneToOneField(AuditoriaDivergencia, on_delete=models.PROTECT, related_name='resolucao')
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    justificativa = models.TextField()
    base_anterior = models.ForeignKey(Base, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    nova_base = models.ForeignKey(Base, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    transferencia = models.ForeignKey(
        Transferencia, null=True, blank=True, on_delete=models.PROTECT,
        related_name='resolucoes_auditoria',
    )
    resolvida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='resolucoes_auditoria',
    )
    resolvida_em = models.DateTimeField(auto_now_add=True)
    dados = models.JSONField(default=dict, blank=True)


class AuditoriaEvento(models.Model):
    auditoria_base = models.ForeignKey(AuditoriaBase, on_delete=models.CASCADE, related_name='eventos')
    divergencia = models.ForeignKey(
        AuditoriaDivergencia, null=True, blank=True, on_delete=models.PROTECT, related_name='eventos',
    )
    tipo = models.CharField(max_length=60, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    dados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['criado_em', 'id']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(_('Eventos de auditoria são imutáveis.'))
        return super().save(*args, **kwargs)
