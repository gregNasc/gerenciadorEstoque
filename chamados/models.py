from datetime import timedelta
from pathlib import Path
import re
import unicodedata
from estoque.models import Base, Empresa, Equipamento, Produto, Sick
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


MIMES_ANEXO_PERMITIDOS = {
    'application/pdf', 'image/png', 'image/jpeg', 'image/webp', 'text/plain',
    'text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}


def normalizar_alias(valor):
    texto = unicodedata.normalize('NFKD', valor or '')
    texto = ''.join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return re.sub(r'\s+', ' ', texto).strip().casefold()


def validar_tamanho_anexo(arquivo):
    limite = 50 * 1024 * 1024
    if arquivo.size > limite:
        raise ValidationError('O ANEXO NÃO PODE ULTRAPASSAR 50 MB.')


def validar_mime_anexo(arquivo):
    content_type = getattr(arquivo, 'content_type', '')
    if content_type and content_type not in MIMES_ANEXO_PERMITIDOS:
        raise ValidationError('O TIPO DE CONTEÚDO DO ANEXO NÃO É PERMITIDO.')


def caminho_anexo(instance, filename):
    return f'chamados/{instance.chamado_id}/{Path(filename).name}'


class CategoriaChamado(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    descricao = models.TextField(blank=True)
    sla_horas = models.PositiveIntegerField(default=24)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nome']
        permissions = [
            ('gerenciar_categorias_chamado', 'Pode gerenciar categorias de chamados'),
        ]

    def __str__(self):
        return self.nome


class SequenciaChamado(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    ano = models.PositiveSmallIntegerField()
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'ano'], name='chamado_sequencia_empresa_ano_unica'
            ),
        ]


class AliasUsuario(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='aliases_chamados'
    )
    alias = models.CharField(max_length=150)
    alias_normalizado = models.CharField(max_length=150, unique=True, editable=False)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['alias_normalizado']

    def save(self, *args, **kwargs):
        self.alias_normalizado = normalizar_alias(self.alias)
        return super().save(*args, **kwargs)


class PendenciaVinculoLider(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        RESOLVIDA = 'RESOLVIDA', 'Resolvida'
        DESCARTADA = 'DESCARTADA', 'Descartada'

    inventario = models.OneToOneField(
        'insumos.Inventario', on_delete=models.CASCADE, related_name='pendencia_lider'
    )
    texto_importado = models.CharField(max_length=150)
    texto_normalizado = models.CharField(max_length=150, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    resolvida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='pendencias_lider_resolvidas',
    )
    resolvida_em = models.DateTimeField(null=True, blank=True)
    justificativa = models.TextField(blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)


class InventarioLiderHistorico(models.Model):
    inventario = models.ForeignKey(
        'insumos.Inventario', on_delete=models.PROTECT, related_name='historico_vinculos_lider'
    )
    lider_anterior = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+'
    )
    lider_novo = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+'
    )
    texto_original = models.CharField(max_length=150, blank=True)
    justificativa = models.TextField()
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='vinculos_lider_alterados'
    )
    alterado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-alterado_em', '-id']


class Chamado(models.Model):
    class MomentoInventario(models.TextChoices):
        ANTES = 'ANTES', _('Antes do inventario')
        EM_ANDAMENTO = 'EM_ANDAMENTO', _('Inventario em andamento')

    class Prioridade(models.TextChoices):
        BAIXA = 'BAIXA', _('Baixa')
        NORMAL = 'NORMAL', _('Normal')
        ALTA = 'ALTA', _('Alta')
        CRITICA = 'CRITICA', _('Crítica')

    class Status(models.TextChoices):
        ABERTO = 'ABERTO', _('Aberto')
        AGUARDANDO_ATENDIMENTO = 'AGUARDANDO_ATENDIMENTO', _('Aguardando atendimento')
        EM_ATENDIMENTO = 'EM_ATENDIMENTO', _('Em atendimento')
        AGUARDANDO_SOLICITANTE = 'AGUARDANDO_SOLICITANTE', _('Aguardando solicitante')
        AGUARDANDO_TERCEIRO = 'AGUARDANDO_TERCEIRO', _('Aguardando terceiro')
        RESOLVIDO = 'RESOLVIDO', _('Resolvido')
        AVALIACAO = 'AVALIACAO', _('Aguardando avaliação')
        ENCERRADO = 'ENCERRADO', _('Encerrado')
        REABERTO = 'REABERTO', _('Reaberto')
        CANCELADO = 'CANCELADO', _('Cancelado')

    protocolo = models.CharField(max_length=30, unique=True, editable=False)
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name='chamados')
    base = models.ForeignKey(Base, on_delete=models.PROTECT, related_name='chamados')
    inventario = models.ForeignKey('insumos.Inventario', null=True, blank=True, on_delete=models.PROTECT, related_name='chamados')
    momento_inventario_abertura = models.CharField(
        max_length=20,
        choices=MomentoInventario.choices,
        blank=True,
        default='',
        db_index=True,
    )
    categoria_equipamento = models.CharField(max_length=50, choices=Produto.CATEGORIAS, blank=True, db_index=True)
    equipamento = models.ForeignKey(Equipamento, null=True, blank=True, on_delete=models.PROTECT, related_name='chamados')
    categoria = models.ForeignKey(CategoriaChamado, null=True, blank=True,  on_delete=models.PROTECT, related_name='chamados')
    loja = models.CharField(max_length=100, blank=True)
    lider = models.CharField(max_length=150, blank=True)
    titulo = models.CharField(max_length=180)
    descricao = models.TextField()
    prioridade = models.CharField(
        max_length=12, choices=Prioridade.choices, default=Prioridade.NORMAL, db_index=True
    )
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.ABERTO, db_index=True
    )
    aberto_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='chamados_abertos'
    )
    atendente = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='chamados_atendidos',
    )
    sick = models.ForeignKey(
        Sick, null=True, blank=True, on_delete=models.PROTECT, related_name='chamados_origem'
    )
    aberto_em = models.DateTimeField(default=timezone.now, db_index=True)
    primeira_resposta_em = models.DateTimeField(null=True, blank=True)
    aceito_em = models.DateTimeField(null=True, blank=True)
    iniciado_em = models.DateTimeField(null=True, blank=True)
    prazo_sla_em = models.DateTimeField(null=True, blank=True, db_index=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)
    fechado_em = models.DateTimeField(null=True, blank=True)
    causa_raiz = models.TextField(blank=True)
    resolucao = models.TextField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-aberto_em', '-id']
        permissions = [
            ('atender_chamado', 'Pode atender chamados'),
            ('visualizar_todos_chamados', 'Pode visualizar todos os chamados'),
            ('exportar_chamados', 'Pode exportar chamados'),
            ('supervisionar_chamado', 'Pode supervisionar chamados'),
            ('visualizar_dashboard_chamado', 'Pode visualizar dashboard de chamados'),
            ('configurar_chamado', 'Pode configurar chamados e vínculos'),
            ('converter_chamado_sick', 'Pode converter chamado em SICK'),
        ]
        indexes = [
            models.Index(fields=['empresa', 'status', 'aberto_em']),
            models.Index(fields=['base', 'status']),
            models.Index(fields=['atendente', 'status']),
        ]

    def clean(self):
        super().clean()
        if self.base_id and self.empresa_id and self.base.empresa_id != self.empresa_id:
            raise ValidationError({'base': 'A BASE NÃO PERTENCE À EMPRESA INFORMADA.'})
        if self.inventario_id and self.inventario.base_id != self.base_id:
            raise ValidationError({'inventario': 'O INVENTÁRIO NÃO PERTENCE À BASE INFORMADA.'})
        if self.equipamento_id and self.equipamento.regional_id != self.base_id:
            raise ValidationError({'equipamento': 'O EQUIPAMENTO NÃO PERTENCE À BASE INFORMADA.'})
        if self.status in {self.Status.RESOLVIDO, self.Status.AVALIACAO, self.Status.ENCERRADO}:
            erros = {}
            if not self.causa_raiz:
                erros['causa_raiz'] = 'INFORME A CAUSA RAIZ DO CHAMADO.'
            if not self.resolucao:
                erros['resolucao'] = 'INFORME A SOLUÇÃO DO CHAMADO.'
            if erros:
                raise ValidationError(erros)

    @property
    def duracao(self):
        fim = self.fechado_em or self.resolvido_em or timezone.now()
        return fim - self.aberto_em

    @property
    def sla_vencido(self):
        return bool(
            self.prazo_sla_em
            and self.status not in {
                self.Status.RESOLVIDO, self.Status.AVALIACAO,
                self.Status.ENCERRADO, self.Status.CANCELADO,
            }
            and timezone.now() > self.prazo_sla_em
        )

    def definir_prazo_sla(self):
        if self.prazo_sla_em:
            return

        sla_horas = 24

        if self.categoria_id:
            sla_horas = self.categoria.sla_horas

        self.prazo_sla_em = (
                self.aberto_em
                + timedelta(hours=sla_horas)
        )


class ChamadoMensagem(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='mensagens')
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='mensagens_chamados'
    )
    texto = models.TextField()
    nota_interna = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['criado_em', 'id']


class ChamadoAnexo(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='anexos')
    mensagem = models.ForeignKey(
        ChamadoMensagem, null=True, blank=True, on_delete=models.CASCADE, related_name='anexos'
    )
    arquivo = models.FileField(
        upload_to=caminho_anexo,
        validators=[
            FileExtensionValidator(
                ['pdf', 'png', 'jpg', 'jpeg', 'webp', 'txt', 'csv', 'xlsx', 'docx']
            ),
            validar_tamanho_anexo,
            validar_mime_anexo,
        ],
    )
    nome_original = models.CharField(max_length=255)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)


class ChamadoEvento(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='eventos')
    tipo = models.CharField(max_length=50)
    descricao = models.TextField()
    dados = models.JSONField(default=dict, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em', '-id']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('EVENTOS DE CHAMADO SÃO IMUTÁVEIS.')
        return super().save(*args, **kwargs)


class ChamadoSessaoAtendimento(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.PROTECT, related_name='sessoes')
    atendente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='sessoes_chamados'
    )
    iniciada_em = models.DateTimeField(default=timezone.now)
    encerrada_em = models.DateTimeField(null=True, blank=True)
    motivo_encerramento = models.CharField(max_length=40, blank=True)
    encerrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+'
    )

    class Meta:
        ordering = ['iniciada_em', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['chamado'],
                condition=models.Q(encerrada_em__isnull=True),
                name='chamado_uma_sessao_aberta',
            ),
        ]

    def clean(self):
        if self.encerrada_em and self.encerrada_em < self.iniciada_em:
            raise ValidationError({'encerrada_em': 'O ENCERRAMENTO NÃO PODE ANTECEDER O INÍCIO.'})


class ChamadoTransferenciaAtendente(models.Model):
    chamado = models.ForeignKey(Chamado, on_delete=models.PROTECT, related_name='transferencias_atendente')
    atendente_anterior = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+'
    )
    atendente_novo = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+'
    )
    motivo = models.TextField()
    transferido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='transferencias_chamado_realizadas',
    )
    transferido_em = models.DateTimeField(auto_now_add=True)


class ChamadoAvaliacao(models.Model):
    chamado = models.OneToOneField(Chamado, on_delete=models.PROTECT, related_name='avaliacao')
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='avaliacoes_chamados'
    )
    nota = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    resolvido = models.BooleanField()
    comentario = models.TextField(blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)


class ChamadoConexaoAtendente(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='conexoes_presenca_chamados',
    )
    canal = models.CharField(max_length=255, unique=True)
    conectado_em = models.DateTimeField(auto_now_add=True)
    visto_em = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['usuario', 'visto_em'])]
