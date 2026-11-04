import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from compras.storage import documento_compra_storage, documento_compra_upload_to
from compras.validators import validar_danfe_pdf, validar_xml_nfe


class CodigoCatalogo(models.Model):
    class Tipo(models.TextChoices):
        EAN_GTIN = 'EAN_GTIN', 'EAN/GTIN'
        CODIGO_FORNECEDOR = 'CODIGO_FORNECEDOR', 'Código do fornecedor'
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


class CatalogoProdutoEmpresa(models.Model):
    """Seleção tenant-specific sobre o cadastro técnico global de produtos."""

    empresa = models.ForeignKey(
        'estoque.Empresa',
        on_delete=models.CASCADE,
        related_name='catalogo_produtos',
    )
    produto = models.ForeignKey(
        'estoque.Produto',
        on_delete=models.CASCADE,
        related_name='catalogos_empresa',
    )
    ativo = models.BooleanField(default=True, db_index=True)
    preco_referencia = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    preco_origem = models.CharField(
        max_length=30,
        default='SEM_PRECO_VALIDADO',
        db_index=True,
    )
    preco_fonte = models.CharField(max_length=255, blank=True)
    preco_fornecedor = models.ForeignKey(
        'insumos.FornecedorInsumo',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='catalogos_empresa_precificados',
    )
    preco_validado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='catalogos_empresa_precos_validados',
    )
    preco_validado_em = models.DateTimeField(null=True, blank=True)
    configurado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='catalogos_produto_configurados',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['empresa__nome', 'produto__categoria', 'produto__descricao']
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'produto'],
                name='catalogo_produto_empresa_unico',
            ),
        ]

    def __str__(self):
        return f'{self.empresa} — {self.produto}'


class CapacidadeCatalogoProdutoEmpresa(models.Model):
    """Capacidade funcional habilitada explicitamente no catálogo do tenant."""

    INDIVIDUALIZAVEL = 'INDIVIDUALIZAVEL'
    POSSUI_PATRIMONIO = 'POSSUI_PATRIMONIO'
    PATRIMONIO_OBRIGATORIO = 'PATRIMONIO_OBRIGATORIO'
    POSSUI_SERIE = 'POSSUI_SERIE'
    SERIE_OBRIGATORIA = 'SERIE_OBRIGATORIA'
    POSSUI_IMEI = 'POSSUI_IMEI'
    PERMITE_SICK = 'PERMITE_SICK'
    PERMITE_MANUTENCAO = 'PERMITE_MANUTENCAO'
    PERMITE_TRANSFERENCIA = 'PERMITE_TRANSFERENCIA'
    PERMITE_INATIVACAO = 'PERMITE_INATIVACAO'
    DADOS_ESPECIALIZADOS = 'DADOS_ESPECIALIZADOS'
    CONECTIVIDADE_MOVEL = 'CONECTIVIDADE_MOVEL'
    ATIVO_LINHA_MOVEL = 'ATIVO_LINHA_MOVEL'
    CUSTODIA_PESSOAL = 'CUSTODIA_PESSOAL'

    CAPACIDADES_LEGADAS_ATIVAS = frozenset({
        INDIVIDUALIZAVEL,
        POSSUI_PATRIMONIO,
        PATRIMONIO_OBRIGATORIO,
        POSSUI_SERIE,
        SERIE_OBRIGATORIA,
        PERMITE_SICK,
        PERMITE_MANUTENCAO,
        PERMITE_TRANSFERENCIA,
        PERMITE_INATIVACAO,
    })

    catalogo = models.ForeignKey(
        CatalogoProdutoEmpresa,
        on_delete=models.CASCADE,
        related_name='capacidades',
    )
    codigo = models.CharField(max_length=50)
    ativa = models.BooleanField(default=True, db_index=True)
    configurado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='capacidades_catalogo_configuradas',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['catalogo__empresa__nome', 'catalogo__produto__descricao', 'codigo']
        constraints = [
            models.UniqueConstraint(
                fields=['catalogo', 'codigo'],
                name='capacidade_catalogo_codigo_unico',
            ),
        ]
        indexes = [
            models.Index(
                fields=['codigo', 'ativa'],
                name='cap_catalogo_codigo_ativo_idx',
            ),
        ]

    def save(self, *args, **kwargs):
        self.codigo = (self.codigo or '').strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.catalogo} — {self.codigo}'


class FornecedorEmpresa(models.Model):
    """Homologação tenant-specific sobre o diretório global de fornecedores."""

    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        HOMOLOGADO = 'HOMOLOGADO', 'Homologado'
        SUSPENSO = 'SUSPENSO', 'Suspenso'
        INATIVO = 'INATIVO', 'Inativo'

    empresa = models.ForeignKey(
        'estoque.Empresa',
        on_delete=models.CASCADE,
        related_name='fornecedores_homologados',
    )
    fornecedor = models.ForeignKey(
        'insumos.FornecedorInsumo',
        on_delete=models.PROTECT,
        related_name='relacionamentos_empresa',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE,
        db_index=True,
    )
    codigo_interno = models.CharField(max_length=80, blank=True)
    observacao = models.TextField(blank=True)
    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='fornecedores_empresa_cadastrados',
    )
    homologado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='fornecedores_empresa_homologados',
    )
    homologado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['empresa__nome', 'fornecedor__nome']
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'fornecedor'],
                name='fornecedor_empresa_unico',
            ),
        ]
        indexes = [
            models.Index(
                fields=['empresa', 'status'],
                name='fornecedor_empresa_status_idx',
            ),
        ]

    def __str__(self):
        return f'{self.empresa} — {self.fornecedor} ({self.get_status_display()})'


class ProcessoCotacao(models.Model):
    class Status(models.TextChoices):
        ABERTO = 'ABERTO', 'Aberto'
        EM_ANALISE = 'EM_ANALISE', 'Em análise'
        DECIDIDO = 'DECIDIDO', 'Decidido'
        CANCELADO = 'CANCELADO', 'Cancelado'

    solicitacao = models.OneToOneField(
        'insumos.SolicitacaoInsumo',
        on_delete=models.PROTECT,
        related_name='processo_cotacao',
    )
    empresa = models.ForeignKey(
        'estoque.Empresa',
        on_delete=models.PROTECT,
        related_name='processos_cotacao',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ABERTO,
        db_index=True,
    )
    proposta_escolhida = models.ForeignKey(
        'CotacaoFornecedor',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    justificativa_decisao = models.TextField(blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='processos_cotacao_criados',
    )
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='processos_cotacao_decididos',
    )
    decidido_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-criado_em', '-id']
        indexes = [
            models.Index(
                fields=['empresa', 'status'],
                name='cotacao_empresa_status_idx',
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.solicitacao_id
            and self.empresa_id
            and self.solicitacao.base.empresa_id != self.empresa_id
        ):
            raise ValidationError({
                'empresa': 'A empresa deve ser a mesma empresa da Base solicitante.'
            })
        if self.proposta_escolhida_id and (
            self.proposta_escolhida.processo_id != self.pk
        ):
            raise ValidationError({
                'proposta_escolhida': 'A proposta escolhida não pertence a este processo.'
            })

    def __str__(self):
        return f'Cotação {self.solicitacao.protocolo}'


class CotacaoFornecedor(models.Model):
    class Status(models.TextChoices):
        RECEBIDA = 'RECEBIDA', 'Recebida'
        ESCOLHIDA = 'ESCOLHIDA', 'Escolhida'
        NAO_SELECIONADA = 'NAO_SELECIONADA', 'Não selecionada'
        DESCLASSIFICADA = 'DESCLASSIFICADA', 'Desclassificada'

    processo = models.ForeignKey(
        ProcessoCotacao,
        on_delete=models.CASCADE,
        related_name='propostas',
    )
    fornecedor_empresa = models.ForeignKey(
        FornecedorEmpresa,
        on_delete=models.PROTECT,
        related_name='cotacoes',
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.RECEBIDA,
        db_index=True,
    )
    numero_proposta = models.CharField(max_length=100, blank=True)
    validade_proposta = models.DateField(null=True, blank=True)
    prazo_entrega_dias = models.PositiveIntegerField(null=True, blank=True)
    frete = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    impostos = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    condicao_pagamento = models.CharField(max_length=200, blank=True)
    observacao = models.TextField(blank=True)
    cadastrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cotacoes_fornecedor_cadastradas',
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['processo', 'fornecedor_empresa__fornecedor__nome']
        constraints = [
            models.UniqueConstraint(
                fields=['processo', 'fornecedor_empresa'],
                name='cotacao_fornecedor_processo_unico',
            ),
            models.CheckConstraint(
                condition=Q(frete__gte=0, impostos__gte=0, desconto__gte=0),
                name='cotacao_componentes_nao_negativos',
            ),
        ]

    def clean(self):
        super().clean()
        if self.processo_id and self.fornecedor_empresa_id:
            if self.fornecedor_empresa.empresa_id != self.processo.empresa_id:
                raise ValidationError({
                    'fornecedor_empresa': 'O fornecedor não pertence à empresa da cotação.'
                })
            if (
                self.fornecedor_empresa.status
                != FornecedorEmpresa.Status.HOMOLOGADO
                or not self.fornecedor_empresa.fornecedor.ativo
            ):
                raise ValidationError({
                    'fornecedor_empresa': 'O fornecedor precisa estar homologado e ativo.'
                })

    @property
    def subtotal(self):
        itens = self.itens.all()
        return sum((item.valor_total for item in itens), Decimal('0'))

    @property
    def valor_total(self):
        return max(
            self.subtotal + self.frete + self.impostos - self.desconto,
            Decimal('0'),
        )

    def __str__(self):
        return f'{self.processo} — {self.fornecedor_empresa.fornecedor}'


class ItemCotacaoFornecedor(models.Model):
    cotacao = models.ForeignKey(
        CotacaoFornecedor,
        on_delete=models.CASCADE,
        related_name='itens',
    )
    item_solicitacao = models.ForeignKey(
        'insumos.ItemSolicitacaoInsumo',
        on_delete=models.PROTECT,
        related_name='itens_cotacao',
    )
    quantidade = models.DecimalField(max_digits=12, decimal_places=2)
    valor_unitario = models.DecimalField(max_digits=14, decimal_places=4)
    numero_ca = models.CharField(max_length=30, blank=True)
    observacao = models.TextField(blank=True)

    class Meta:
        ordering = ['item_solicitacao_id']
        constraints = [
            models.UniqueConstraint(
                fields=['cotacao', 'item_solicitacao'],
                name='cotacao_item_solicitacao_unico',
            ),
            models.CheckConstraint(
                condition=Q(quantidade__gt=0),
                name='cotacao_item_quantidade_positiva',
            ),
            models.CheckConstraint(
                condition=Q(valor_unitario__gte=0),
                name='cotacao_item_valor_nao_negativo',
            ),
        ]

    def clean(self):
        super().clean()
        if self.cotacao_id and self.item_solicitacao_id and (
            self.item_solicitacao.solicitacao_id
            != self.cotacao.processo.solicitacao_id
        ):
            raise ValidationError({
                'item_solicitacao': 'O item não pertence à solicitação cotada.'
            })

    @property
    def valor_total(self):
        return self.quantidade * self.valor_unitario

    def __str__(self):
        return f'{self.cotacao} — {self.item_solicitacao.descricao_exibicao}'


class Aquisicao(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = 'RASCUNHO', 'Rascunho'
        APROVADA = 'APROVADA', 'Aprovada'
        EM_RECEBIMENTO = 'EM_RECEBIMENTO', 'Em recebimento'
        RECEBIDA = 'RECEBIDA', 'Recebida'
        CANCELADA = 'CANCELADA', 'Cancelada'

    empresa = models.ForeignKey('estoque.Empresa', on_delete=models.PROTECT, related_name='aquisicoes')
    base_destino = models.ForeignKey(
        'estoque.Base',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='aquisicoes_destinadas',
    )
    fornecedor = models.ForeignKey(
        'insumos.FornecedorInsumo', on_delete=models.PROTECT, related_name='aquisicoes'
    )
    processo_cotacao = models.OneToOneField(
        ProcessoCotacao,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='aquisicao_gerada',
    )
    proposta_origem = models.OneToOneField(
        CotacaoFornecedor,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='aquisicao_gerada',
    )
    numero_documento = models.CharField(max_length=80, blank=True, db_index=True)
    chave_nfe = models.CharField(max_length=44, blank=True, db_index=True)
    arquivo_danfe_pdf = models.FileField(
        storage=documento_compra_storage,
        upload_to=documento_compra_upload_to,
        validators=[validar_danfe_pdf],
        blank=True,
    )
    arquivo_xml_nfe = models.FileField(
        storage=documento_compra_storage,
        upload_to=documento_compra_upload_to,
        validators=[validar_xml_nfe],
        blank=True,
    )
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
    frete_cotacao = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    impostos_cotacao = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    desconto_cotacao = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-data_compra', '-id']
        permissions = [
            ('gerenciar_aquisicoes', 'Pode gerenciar aquisições'),
            ('exportar_documentos_aquisicao', 'Pode baixar documentos de aquisições'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['empresa', 'chave_nfe'], condition=~Q(chave_nfe=''),
                name='compra_chave_nfe_empresa_unica',
            ),
            models.CheckConstraint(
                condition=(
                    Q(processo_cotacao__isnull=True, proposta_origem__isnull=True)
                    | Q(processo_cotacao__isnull=False, proposta_origem__isnull=False)
                ),
                name='compra_origem_cotacao_completa',
            ),
            models.CheckConstraint(
                condition=Q(
                    frete_cotacao__gte=0,
                    impostos_cotacao__gte=0,
                    desconto_cotacao__gte=0,
                ),
                name='compra_cotacao_componentes_nao_negativos',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.base_destino_id
            and self.empresa_id
            and self.base_destino.empresa_id != self.empresa_id
        ):
            errors['base_destino'] = 'A Base de destino deve pertencer à empresa da aquisição.'
        if bool(self.processo_cotacao_id) != bool(self.proposta_origem_id):
            errors['processo_cotacao'] = (
                'Processo e proposta de origem devem ser informados em conjunto.'
            )
        if self.processo_cotacao_id and self.proposta_origem_id:
            if self.processo_cotacao.empresa_id != self.empresa_id:
                errors['processo_cotacao'] = 'A cotação pertence a outra empresa.'
            if self.proposta_origem.processo_id != self.processo_cotacao_id:
                errors['proposta_origem'] = 'A proposta não pertence à cotação informada.'
            if self.processo_cotacao.proposta_escolhida_id != self.proposta_origem_id:
                errors['proposta_origem'] = 'A proposta não é a escolhida nesta cotação.'
            if self.proposta_origem.fornecedor_empresa.fornecedor_id != self.fornecedor_id:
                errors['fornecedor'] = 'O fornecedor difere da proposta escolhida.'
        if self.chave_nfe and (len(self.chave_nfe) != 44 or not self.chave_nfe.isdigit()):
            errors['chave_nfe'] = 'A chave da NF-e deve conter exatamente 44 dígitos.'
        for campo, extensao in (('arquivo_danfe_pdf', '.pdf'), ('arquivo_xml_nfe', '.xml')):
            arquivo = getattr(self, campo)
            if arquivo and not arquivo.name.lower().endswith(extensao):
                errors[campo] = f'O arquivo deve ter extensão {extensao}.'
        if errors:
            raise ValidationError(errors)

    @property
    def valor_total(self):
        subtotal = sum((item.valor_total for item in self.itens.all()), Decimal('0'))
        return max(
            subtotal + self.frete_cotacao + self.impostos_cotacao - self.desconto_cotacao,
            Decimal('0'),
        )

    def __str__(self):
        return self.numero_documento or f'Aquisição #{self.pk or "nova"}'


class NotaFiscalAquisicao(models.Model):
    class Situacao(models.TextChoices):
        PROCESSADA = 'PROCESSADA', 'Processada'
        DIVERGENTE = 'DIVERGENTE', 'Processada com divergências'

    aquisicao = models.OneToOneField(
        Aquisicao,
        on_delete=models.CASCADE,
        related_name='nota_fiscal',
    )
    chave_acesso = models.CharField(max_length=44, db_index=True)
    numero = models.CharField(max_length=30)
    serie = models.CharField(max_length=10, blank=True)
    data_emissao = models.DateTimeField(null=True, blank=True)
    emitente_cnpj = models.CharField(max_length=14, blank=True)
    emitente_nome = models.CharField(max_length=255, blank=True)
    valor_produtos = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    valor_frete = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    valor_desconto = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    valor_impostos = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    valor_nota = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    situacao = models.CharField(
        max_length=20,
        choices=Situacao.choices,
        default=Situacao.PROCESSADA,
        db_index=True,
    )
    divergencias = models.JSONField(default=list, blank=True)
    hash_xml = models.CharField(max_length=64, db_index=True)
    processado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='notas_fiscais_processadas',
    )
    processado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-processado_em', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['aquisicao', 'hash_xml'],
                name='compra_nfe_aquisicao_hash_unico',
            ),
        ]

    def __str__(self):
        return f'NF-e {self.numero}/{self.serie or "-"}'


class ItemNotaFiscalAquisicao(models.Model):
    class StatusCatalogo(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente de análise'
        SUGERIDO = 'SUGERIDO', 'Correspondência sugerida'
        CONFIRMADO = 'CONFIRMADO', 'Correspondência confirmada'
        NAO_ENCONTRADO = 'NAO_ENCONTRADO', 'Não encontrado no catálogo'

    nota_fiscal = models.ForeignKey(
        NotaFiscalAquisicao,
        on_delete=models.CASCADE,
        related_name='itens',
    )
    numero_item = models.PositiveIntegerField()
    codigo_fornecedor = models.CharField(max_length=100, blank=True)
    ean_gtin = models.CharField(max_length=30, blank=True)
    descricao = models.CharField(max_length=500)
    ncm = models.CharField(max_length=12, blank=True)
    cfop = models.CharField(max_length=10, blank=True)
    unidade = models.CharField(max_length=20, blank=True)
    quantidade = models.DecimalField(max_digits=16, decimal_places=4)
    valor_unitario = models.DecimalField(max_digits=16, decimal_places=6)
    valor_total = models.DecimalField(max_digits=16, decimal_places=2)
    status_catalogo = models.CharField(
        max_length=20,
        choices=StatusCatalogo.choices,
        default=StatusCatalogo.PENDENTE,
        db_index=True,
    )
    produto_catalogo = models.ForeignKey(
        'estoque.Produto',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='itens_nfe_resolvidos',
    )
    insumo_catalogo = models.ForeignKey(
        'insumos.Insumo',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='itens_nfe_resolvidos',
    )
    codigo_catalogo = models.ForeignKey(
        CodigoCatalogo,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='itens_nfe_resolvidos',
    )
    criterio_catalogo = models.CharField(max_length=80, blank=True)
    resolvido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='itens_nfe_resolvidos',
    )
    resolvido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['numero_item', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['nota_fiscal', 'numero_item'],
                name='compra_nfe_item_numero_unico',
            ),
            models.CheckConstraint(
                condition=Q(quantidade__gte=0),
                name='compra_nfe_item_quantidade_nao_negativa',
            ),
            models.CheckConstraint(
                condition=Q(valor_unitario__gte=0, valor_total__gte=0),
                name='compra_nfe_item_valores_nao_negativos',
            ),
            models.CheckConstraint(
                condition=(
                    Q(produto_catalogo__isnull=True, insumo_catalogo__isnull=True)
                    | Q(produto_catalogo__isnull=False, insumo_catalogo__isnull=True)
                    | Q(produto_catalogo__isnull=True, insumo_catalogo__isnull=False)
                ),
                name='compra_nfe_item_uma_referencia_catalogo',
            ),
        ]

    def __str__(self):
        return f'{self.numero_item} — {self.descricao}'


class ItemAquisicao(models.Model):
    class Tipo(models.TextChoices):
        EQUIPAMENTO = 'EQUIPAMENTO', 'Equipamento'
        INSUMO = 'INSUMO', 'Insumo'

    aquisicao = models.ForeignKey(Aquisicao, on_delete=models.CASCADE, related_name='itens')
    item_cotacao_origem = models.OneToOneField(
        ItemCotacaoFornecedor,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='item_aquisicao_gerado',
    )
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

    def clean(self):
        super().clean()
        if self.item_cotacao_origem_id and self.aquisicao_id:
            if (
                self.aquisicao.proposta_origem_id
                != self.item_cotacao_origem.cotacao_id
            ):
                raise ValidationError({
                    'item_cotacao_origem': (
                        'O item cotado não pertence à proposta de origem da aquisição.'
                    ),
                })
        if (
            self.tipo_item == self.Tipo.EQUIPAMENTO
            and self.produto_id
            and self.aquisicao_id
        ):
            if not CatalogoProdutoEmpresa.objects.filter(
                empresa_id=self.aquisicao.empresa_id,
                produto_id=self.produto_id,
                ativo=True,
            ).exists():
                raise ValidationError({
                    'produto': 'O equipamento não está habilitado no catálogo desta empresa.'
                })

    @property
    def valor_total(self):
        return (self.quantidade * self.valor_unitario) - self.desconto + self.frete + self.impostos


class VinculoEquipamentoAquisicao(models.Model):
    item = models.ForeignKey(ItemAquisicao, on_delete=models.PROTECT, related_name='equipamentos_vinculados')
    item_remessa = models.ForeignKey(
        'ItemRemessaCompra',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='equipamentos_individualizados',
    )
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
        if (
            self.item_id
            and self.equipamento_id
            and self.item.aquisicao.empresa_id != self.equipamento.regional.empresa_id
        ):
            raise ValidationError(
                {'equipamento': 'O equipamento deve pertencer à empresa da aquisição.'}
            )
        if self.item_remessa_id:
            if self.item_remessa.item_aquisicao_id != self.item_id:
                raise ValidationError({
                    'item_remessa': 'A unidade não pertence ao item recebido desta aquisição.'
                })
            if self.item_remessa.produto_id != self.equipamento.produto_id:
                raise ValidationError({
                    'equipamento': 'O modelo da unidade difere do item recebido.'
                })
            if self.item_remessa.remessa.base_destino_id != self.equipamento.regional_id:
                raise ValidationError({
                    'equipamento': 'A unidade deve ser cadastrada na Base que recebeu a remessa.'
                })


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


class HistoricoPrecoProduto(models.Model):
    empresa = models.ForeignKey(
        'estoque.Empresa',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='historicos_preco_produto',
    )
    produto = models.ForeignKey(
        'estoque.Produto',
        on_delete=models.PROTECT,
        related_name='historico_precos',
    )
    valor_anterior = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    valor_novo = models.DecimalField(max_digits=14, decimal_places=4)
    origem_anterior = models.CharField(max_length=30, blank=True)
    origem_nova = models.CharField(max_length=30)
    fonte = models.CharField(max_length=255, blank=True)
    fornecedor = models.ForeignKey(
        'insumos.FornecedorInsumo', null=True, blank=True, on_delete=models.PROTECT,
    )
    observacao = models.TextField(blank=True)
    alterado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    alterado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-alterado_em', '-id']
        indexes = [models.Index(fields=['produto', 'alterado_em'])]


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
        if self.base_origem_id and self.base_origem.empresa_id != self.empresa_id:
            raise ValidationError({'base_origem': 'A base de origem deve pertencer à empresa.'})
        if self.aquisicao_id and self.aquisicao.empresa_id != self.empresa_id:
            raise ValidationError({'aquisicao': 'A aquisição deve pertencer à empresa da remessa.'})
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
    item_nfe = models.ForeignKey(
        ItemNotaFiscalAquisicao,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='itens_remessa',
    )
    insumo = models.ForeignKey('insumos.Insumo', null=True, blank=True, on_delete=models.PROTECT)
    equipamento = models.ForeignKey('estoque.Equipamento', null=True, blank=True, on_delete=models.PROTECT)
    produto = models.ForeignKey(
        'estoque.Produto',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='itens_remessa_compra',
    )
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
                    Q(insumo__isnull=False, equipamento__isnull=True, produto__isnull=True)
                    | Q(insumo__isnull=True, equipamento__isnull=False, produto__isnull=True)
                    | Q(insumo__isnull=True, equipamento__isnull=True, produto__isnull=False)
                ),
                name='remessa_item_uma_referencia',
            ),
        ]

    @property
    def descricao_exibicao(self):
        if self.insumo_id:
            return str(self.insumo)
        if self.equipamento_id:
            return str(self.equipamento)
        if self.produto_id:
            return self.produto.descricao
        return 'Item não identificado'

    @property
    def quantidade_pendente_individualizacao(self):
        if not self.produto_id:
            return Decimal('0')
        vinculados = self.equipamentos_individualizados.count()
        return max(self.quantidade_recebida - Decimal(vinculados), Decimal('0'))

    def clean(self):
        super().clean()
        if self.item_aquisicao_id and self.remessa_id:
            if self.item_aquisicao.aquisicao_id != self.remessa.aquisicao_id:
                raise ValidationError({
                    'item_aquisicao': 'O item não pertence à aquisição da remessa.'
                })
            if self.produto_id and self.item_aquisicao.produto_id != self.produto_id:
                raise ValidationError({'produto': 'O equipamento difere do item da aquisição.'})
            if self.insumo_id and self.item_aquisicao.insumo_id != self.insumo_id:
                raise ValidationError({'insumo': 'O insumo difere do item da aquisição.'})
            if self.equipamento_id and (
                self.item_aquisicao.produto_id != self.equipamento.produto_id
            ):
                raise ValidationError({'equipamento': 'O ativo difere do item da aquisição.'})
        if self.item_nfe_id and self.remessa_id:
            if self.item_nfe.nota_fiscal.aquisicao_id != self.remessa.aquisicao_id:
                raise ValidationError({
                    'item_nfe': 'O item fiscal não pertence à aquisição da remessa.'
                })
            if self.item_nfe.status_catalogo != ItemNotaFiscalAquisicao.StatusCatalogo.CONFIRMADO:
                raise ValidationError({
                    'item_nfe': 'Confirme a correspondência do item fiscal antes do recebimento.'
                })
        if self.item_nfe_id:
            if self.produto_id and self.item_nfe.produto_catalogo_id != self.produto_id:
                raise ValidationError({'produto': 'O equipamento difere do item da NF-e.'})
            if self.insumo_id and self.item_nfe.insumo_catalogo_id != self.insumo_id:
                raise ValidationError({'insumo': 'O insumo difere do item da NF-e.'})
            if self.equipamento_id and (
                self.item_nfe.produto_catalogo_id != self.equipamento.produto_id
            ):
                raise ValidationError({'equipamento': 'O ativo difere do item da NF-e.'})


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
    quantidade_esperada_aquisicao = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
    )
    quantidade_esperada_nfe = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    observacao = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantidade_recebida__gte=0), name='recebimento_qtd_nao_negativa'),
            models.CheckConstraint(condition=Q(quantidade_avariada__gte=0), name='recebimento_avaria_nao_negativa'),
            models.CheckConstraint(condition=Q(quantidade_faltante__gte=0), name='recebimento_falta_nao_negativa'),
        ]


class DivergenciaRecebimentoCompra(models.Model):
    class Tipo(models.TextChoices):
        AVARIA = 'AVARIA', 'Item avariado'
        FALTA = 'FALTA', 'Quantidade faltante'
        QUANTIDADE_AQUISICAO = 'QUANTIDADE_AQUISICAO', 'Quantidade diferente da aquisição'
        QUANTIDADE_NFE = 'QUANTIDADE_NFE', 'Quantidade diferente da NF-e'
        ITEM_SEM_NFE = 'ITEM_SEM_NFE', 'Item sem correspondência na NF-e'
        ITEM_INESPERADO = 'ITEM_INESPERADO', 'Item inesperado'

    recebimento = models.ForeignKey(
        RecebimentoRemessa,
        on_delete=models.PROTECT,
        related_name='divergencias',
    )
    item = models.ForeignKey(
        ItemRemessaCompra,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='divergencias_recebimento',
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices, db_index=True)
    quantidade_esperada = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    quantidade_informada = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
    )
    descricao = models.CharField(max_length=500, blank=True)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['criado_em', 'id']

    def __str__(self):
        return self.get_tipo_display()


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
