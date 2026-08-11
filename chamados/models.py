from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from estoque.models import Base, Empresa


def validar_tamanho_anexo(arquivo):
    limite = 10 * 1024 * 1024
    if arquivo.size > limite:
        raise ValidationError('O ANEXO NÃO PODE ULTRAPASSAR 10 MB.')


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


class Chamado(models.Model):
    class Prioridade(models.TextChoices):
        BAIXA = 'BAIXA', 'Baixa'
        NORMAL = 'NORMAL', 'Normal'
        ALTA = 'ALTA', 'Alta'
        CRITICA = 'CRITICA', 'Crítica'

    class Status(models.TextChoices):
        ABERTO = 'ABERTO', 'Aberto'
        EM_ATENDIMENTO = 'EM_ATENDIMENTO', 'Em atendimento'
        AGUARDANDO_USUARIO = 'AGUARDANDO_USUARIO', 'Aguardando usuário'
        RESOLVIDO = 'RESOLVIDO', 'Resolvido'
        FECHADO = 'FECHADO', 'Fechado'
        CANCELADO = 'CANCELADO', 'Cancelado'

    protocolo = models.CharField(max_length=30, unique=True, editable=False)
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name='chamados')
    base = models.ForeignKey(Base, on_delete=models.PROTECT, related_name='chamados')
    inventario = models.ForeignKey(
        'insumos.Inventario', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='chamados',
    )
    categoria = models.ForeignKey(
        CategoriaChamado, on_delete=models.PROTECT, related_name='chamados'
    )
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
    aberto_em = models.DateTimeField(default=timezone.now, db_index=True)
    iniciado_em = models.DateTimeField(null=True, blank=True)
    prazo_sla_em = models.DateTimeField(null=True, blank=True, db_index=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)
    fechado_em = models.DateTimeField(null=True, blank=True)
    resolucao = models.TextField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-aberto_em', '-id']
        permissions = [
            ('atender_chamado', 'Pode atender chamados'),
            ('visualizar_todos_chamados', 'Pode visualizar todos os chamados'),
            ('exportar_chamados', 'Pode exportar chamados'),
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
        if self.status in {self.Status.RESOLVIDO, self.Status.FECHADO} and not self.resolucao:
            raise ValidationError({'resolucao': 'INFORME A RESOLUÇÃO DO CHAMADO.'})

    @property
    def duracao(self):
        fim = self.fechado_em or self.resolvido_em or timezone.now()
        return fim - self.aberto_em

    @property
    def sla_vencido(self):
        return bool(
            self.prazo_sla_em
            and self.status not in {self.Status.RESOLVIDO, self.Status.FECHADO, self.Status.CANCELADO}
            and timezone.now() > self.prazo_sla_em
        )

    def definir_prazo_sla(self):
        if not self.prazo_sla_em and self.categoria_id:
            self.prazo_sla_em = self.aberto_em + timedelta(hours=self.categoria.sla_horas)

    def __str__(self):
        return f'{self.protocolo} - {self.titulo}'


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
