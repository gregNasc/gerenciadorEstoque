import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class CodigoCatalogo(models.Model):
    class Tipo(models.TextChoices):
        EAN_GTIN = 'EAN_GTIN', 'EAN/GTIN'
        CAIXA = 'CAIXA', 'Caixa ou pacote'
        SKU_FABRICANTE = 'SKU_FABRICANTE', 'SKU do fabricante'
        INTERNO = 'INTERNO', 'Código interno'

    empresa = models.ForeignKey('estoque.Empresa', on_delete=models.CASCADE, related_name='codigos_catalogo')
    produto = models.ForeignKey(
        'estoque.Produto', null=True, blank=True, on_delete=models.PROTECT, related_name='codigos_catalogo'
    )
    insumo = models.ForeignKey(
        'insumos.Insumo', null=True, blank=True, on_delete=models.PROTECT, related_name='codigos_catalogo'
    )
    tipo = models.CharField(max_length=25, choices=Tipo.choices)
    codigo = models.CharField(max_length=100)
    fator_conversao = models.DecimalField(max_digits=12, decimal_places=4, default=1)
    ativo = models.BooleanField(default=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['empresa', 'tipo', 'codigo'], name='catalogo_codigo_empresa_unico'),
            models.CheckConstraint(condition=Q(fator_conversao__gt=0), name='catalogo_fator_positivo'),
            models.CheckConstraint(
                condition=(
                    Q(produto__isnull=False, insumo__isnull=True)
                    | Q(produto__isnull=True, insumo__isnull=False)
                ),
                name='catalogo_codigo_uma_referencia',
            ),
        ]


class Aquisicao(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = 'RASCUNHO', 'Rascunho'
        APROVADA = 'APROVADA', 'Aprovada'
        EM_RECEBIMENTO = 'EM_RECEBIMENTO', 'Em recebimento'
        RECEBIDA = 'RECEBIDA', 'Recebida'
        CANCELADA = 'CANCELADA', 'Cancelada'

    empresa = models.ForeignKey('estoque.Empresa', on_delete=models.PROTECT, related_name='aquisicoes')
    fornecedor = models.ForeignKey(
        'insumos.FornecedorInsumo', on_delete=models.PROTECT, related_name='aquisicoes'
    )
    numero_documento = models.CharField(max_length=80, blank=True, db_index=True)
    chave_nfe = models.CharField(max_length=44, blank=True, db_index=True)
    arquivo_danfe_pdf = models.FileField(upload_to='compras/danfe/%Y/%m/', blank=True)
    arquivo_xml_nfe = models.FileField(upload_to='compras/xml/%Y/%m/', blank=True)
    numero_pedido_compra = models.CharField(max_length=80, blank=True, db_index=True)
    centro_custo = models.CharField(max_length=100, blank=True)
    data_compra = models.DateField(default=timezone.localdate, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO, db_index=True)
    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='aquisicoes_cadastradas'
    )
    aprovado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='aquisicoes_aprovadas',
    )
    aprovado_em = models.DateTimeField(null=True, blank=True)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-data_compra', '-id']
        permissions = [('gerenciar_aquisicoes', 'Pode gerenciar aquisições')]
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'chave_nfe'], condition=~Q(chave_nfe=''),
                name='compra_chave_nfe_empresa_unica',
            ),
        ]

    def clean(self):
        super().clean()
        if self.chave_nfe and (len(self.chave_nfe) != 44 or not self.chave_nfe.isdigit()):
            raise ValidationError({'chave_nfe': 'A chave da NF-e deve conter exatamente 44 dígitos.'})
        for campo, extensao in (('arquivo_danfe_pdf', '.pdf'), ('arquivo_xml_nfe', '.xml')):
            arquivo = getattr(self, campo)
            if arquivo and not arquivo.name.lower().endswith(extensao):
                raise ValidationError({campo: f'O arquivo deve ter extensão {extensao}.'})

    @property
    def valor_total(self):
        return sum((item.valor_total for item in self.itens.all()), Decimal('0'))

    def __str__(self):
        return self.numero_documento or f'Aquisição #{self.pk or "nova"}'


class ItemAquisicao(models.Model):
    class Tipo(models.TextChoices):
        EQUIPAMENTO = 'EQUIPAMENTO', 'Equipamento'
        INSUMO = 'INSUMO', 'Insumo'

    aquisicao = models.ForeignKey(Aquisicao, on_delete=models.CASCADE, related_name='itens')
    tipo_item = models.CharField(max_length=15, choices=Tipo.choices)
    produto = models.ForeignKey('estoque.Produto', null=True, blank=True, on_delete=models.PROTECT)
    insumo = models.ForeignKey('insumos.Insumo', null=True, blank=True, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=14, decimal_places=2)
    valor_unitario = models.DecimalField(max_digits=14, decimal_places=4)
    desconto = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    frete = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    impostos = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observacao = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantidade__gt=0), name='compra_item_quantidade_positiva'),
            models.CheckConstraint(condition=Q(valor_unitario__gte=0), name='compra_item_valor_nao_negativo'),
            models.CheckConstraint(
                condition=(
                    Q(tipo_item='EQUIPAMENTO', produto__isnull=False, insumo__isnull=True)
                    | Q(tipo_item='INSUMO', produto__isnull=True, insumo__isnull=False)
                ),
                name='compra_item_referencia_compativel',
            ),
        ]

    @property
    def valor_total(self):
        return (self.quantidade * self.valor_unitario) - self.desconto + self.frete + self.impostos


class VinculoEquipamentoAquisicao(models.Model):
    item = models.ForeignKey(ItemAquisicao, on_delete=models.PROTECT, related_name='equipamentos_vinculados')
    equipamento = models.OneToOneField(
        'estoque.Equipamento', on_delete=models.PROTECT, related_name='vinculo_aquisicao'
    )
    valor_aquisicao_snapshot = models.DecimalField(max_digits=14, decimal_places=4)
    criado_em = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.item_id and self.item.tipo_item != ItemAquisicao.Tipo.EQUIPAMENTO:
            raise ValidationError({'item': 'O item deve ser do tipo equipamento.'})
        if self.item_id and self.equipamento_id and self.item.produto_id != self.equipamento.produto_id:
            raise ValidationError({'equipamento': 'O produto do equipamento difere do item da aquisição.'})


class HistoricoValorEquipamento(models.Model):
    equipamento = models.ForeignKey(
        'estoque.Equipamento', on_delete=models.PROTECT, related_name='historico_valores'
    )
    custo_anterior = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    custo_novo = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    referencia_anterior = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    referencia_nova = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    origem_anterior = models.CharField(max_length=30, blank=True)
    origem_nova = models.CharField(max_length=30, blank=True)
    motivo = models.TextField()
    alterado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    alterado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-alterado_em', '-id']


class RemessaCompra(models.Model):
    class Fluxo(models.TextChoices):
        FORNECEDOR_DIRETO = 'FORNECEDOR_DIRETO', 'Fornecedor para base'
        VIA_MATRIZ = 'VIA_MATRIZ', 'Fornecedor para matriz'
        ENTRE_BASES = 'ENTRE_BASES', 'Transferência entre bases'

    class Status(models.TextChoices):
        PREPARADA = 'PREPARADA', 'Preparada'
        EM_TRANSITO = 'EM_TRANSITO', 'Em trânsito'
        AGUARDANDO_CONFERENCIA = 'AGUARDANDO_CONFERENCIA', 'Aguardando conferência'
        RECEBIDA = 'RECEBIDA', 'Recebida'
        RECEBIDA_PARCIAL = 'RECEBIDA_PARCIAL', 'Recebida parcialmente'
        RECEBIDA_DIVERGENCIA = 'RECEBIDA_DIVERGENCIA', 'Recebida com divergência'
        CANCELADA = 'CANCELADA', 'Cancelada'

    protocolo = models.CharField(max_length=32, unique=True, default='', editable=False)
    aquisicao = models.ForeignKey(
        Aquisicao, null=True, blank=True, on_delete=models.PROTECT, related_name='remessas'
    )
    empresa = models.ForeignKey('estoque.Empresa', on_delete=models.PROTECT, related_name='remessas_compra')
    fluxo = models.CharField(max_length=25, choices=Fluxo.choices)
    base_origem = models.ForeignKey(
        'estoque.Base', null=True, blank=True, on_delete=models.PROTECT, related_name='remessas_compra_saida'
    )
    base_destino = models.ForeignKey(
        'estoque.Base', on_delete=models.PROTECT, related_name='remessas_compra_entrada'
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PREPARADA, db_index=True)
    criada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='remessas_criadas')
    enviada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='remessas_enviadas',
    )
    enviada_em = models.DateTimeField(null=True, blank=True)
    previsao_chegada = models.DateField(null=True, blank=True)
    codigo_rastreio = models.CharField(max_length=100, blank=True)
    observacao = models.TextField(blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [
            ('criar_remessa_compra', 'Pode criar remessa de compra'),
            ('confirmar_remessa_compra', 'Pode confirmar remessa de compra'),
        ]

    def save(self, *args, **kwargs):
        if not self.protocolo:
            self.protocolo = f'REM-{timezone.localdate():%y%m%d}-{uuid.uuid4().hex[:8].upper()}'
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.base_destino_id and self.base_destino.empresa_id != self.empresa_id:
            raise ValidationError({'base_destino': 'A base de destino deve pertencer à empresa.'})
        if self.fluxo == self.Fluxo.ENTRE_BASES:
            if not self.base_origem_id:
                raise ValidationError({'base_origem': 'Informe a base de origem.'})
            if self.base_origem_id == self.base_destino_id:
                raise ValidationError({'base_destino': 'Origem e destino devem ser diferentes.'})
        elif self.base_origem_id:
            raise ValidationError({'base_origem': 'Remessa de fornecedor não usa origem fictícia.'})
        if self.fluxo != self.Fluxo.ENTRE_BASES and not self.aquisicao_id:
            raise ValidationError({'aquisicao': 'Vincule a aquisição à remessa do fornecedor.'})


class ItemRemessaCompra(models.Model):
    remessa = models.ForeignKey(RemessaCompra, on_delete=models.CASCADE, related_name='itens')
    item_aquisicao = models.ForeignKey(
        ItemAquisicao, null=True, blank=True, on_delete=models.PROTECT, related_name='itens_remessa'
    )
    insumo = models.ForeignKey('insumos.Insumo', null=True, blank=True, on_delete=models.PROTECT)
    equipamento = models.ForeignKey('estoque.Equipamento', null=True, blank=True, on_delete=models.PROTECT)
    quantidade_prevista = models.DecimalField(max_digits=14, decimal_places=2, default=1)
    quantidade_recebida = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantidade_avariada = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantidade_faltante = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    custo_unitario_snapshot = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    lote = models.CharField(max_length=100, blank=True)
    validade = models.DateField(null=True, blank=True)
    observacao = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantidade_prevista__gt=0), name='remessa_item_previsto_positivo'),
            models.CheckConstraint(
                condition=(
                    Q(insumo__isnull=False, equipamento__isnull=True)
                    | Q(insumo__isnull=True, equipamento__isnull=False)
                ),
                name='remessa_item_uma_referencia',
            ),
        ]


class RecebimentoRemessa(models.Model):
    remessa = models.ForeignKey(RemessaCompra, on_delete=models.PROTECT, related_name='recebimentos')
    idempotency_key = models.UUIDField()
    recebido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recebido_em = models.DateTimeField(auto_now_add=True)
    finaliza_conferencia = models.BooleanField(default=False)
    observacao = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['remessa', 'idempotency_key'], name='remessa_recebimento_idempotente')
        ]


class LinhaRecebimentoRemessa(models.Model):
    recebimento = models.ForeignKey(RecebimentoRemessa, on_delete=models.PROTECT, related_name='linhas')
    item = models.ForeignKey(ItemRemessaCompra, on_delete=models.PROTECT, related_name='linhas_recebimento')
    quantidade_recebida = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantidade_avariada = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantidade_faltante = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observacao = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantidade_recebida__gte=0), name='recebimento_qtd_nao_negativa'),
            models.CheckConstraint(condition=Q(quantidade_avariada__gte=0), name='recebimento_avaria_nao_negativa'),
            models.CheckConstraint(condition=Q(quantidade_faltante__gte=0), name='recebimento_falta_nao_negativa'),
        ]


class EventoCompra(models.Model):
    aquisicao = models.ForeignKey(
        Aquisicao, null=True, blank=True, on_delete=models.CASCADE, related_name='eventos'
    )
    remessa = models.ForeignKey(
        RemessaCompra, null=True, blank=True, on_delete=models.CASCADE, related_name='eventos'
    )
    tipo = models.CharField(max_length=60, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    dados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['criado_em', 'id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(aquisicao__isnull=False, remessa__isnull=True)
                    | Q(aquisicao__isnull=True, remessa__isnull=False)
                ),
                name='evento_compra_um_agregado',
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Eventos de compra são imutáveis.')
        return super().save(*args, **kwargs)
