from decimal import Decimal

from django.db import models
from estoque.models import Base
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import F, Q
from django.utils import timezone

class CategoriaInsumo(models.Model):
    nome = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nome

class Insumo(models.Model):

    TIPO_CONTROLE = [
        ('QUANTIDADE', 'Quantidade'),
        ('LOTE', 'Lote/Faixa'),
        ('REUTILIZAVEL', 'Reutilizável'),
    ]

    descricao = models.CharField(max_length=150)
    termo_pesquisa_online = models.CharField(
        max_length=255,
        blank=True,
        help_text='Termo usado para localizar este insumo nos catálogos dos fornecedores.',
    )

    categoria = models.ForeignKey(CategoriaInsumo, on_delete=models.PROTECT)
    unidade_medida = models.CharField(max_length=20)
    tipo_controle = models.CharField(max_length=20, choices=TIPO_CONTROLE, default='QUANTIDADE')
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    valor_medio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    preco_referencia = models.ForeignKey(
        'PrecoFornecedorInsumo',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='insumos_como_referencia',
    )
    estoque_minimo = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('2.00'),
        validators=[
            MinValueValidator(Decimal('0.00')),
            MaxValueValidator(Decimal('10.00')),
        ],
    )
    estoque_maximo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    estoque_minimo__gte=Decimal('0.00'),
                    estoque_minimo__lte=Decimal('10.00'),
                ),
                name='insumo_estoque_minimo_entre_0_e_10',
            ),
        ]

    def __str__(self):
        return self.descricao

class FornecedorInsumo(models.Model):
    FONTES_ONLINE = [
        ('GIMBA', 'Gimba'),
        ('FIDELITY', 'Fidelity Suprimentos'),
    ]

    nome = models.CharField(max_length=160, unique=True)
    documento = models.CharField(max_length=30, unique=True, db_index=True)
    site = models.URLField(max_length=300, blank=True)
    fonte_online = models.CharField(
        max_length=40,
        choices=FONTES_ONLINE,
        blank=True,
        db_index=True,
    )
    contato = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    nome_fantasia = models.CharField(max_length=160, blank=True)
    contato_financeiro = models.CharField(max_length=160, blank=True)
    contato_suporte = models.CharField(max_length=160, blank=True)
    email_financeiro = models.EmailField(blank=True)
    email_suporte = models.EmailField(blank=True)
    canais_alternativos = models.TextField(blank=True)
    condicoes_pagamento = models.TextField(blank=True)
    politica_frete = models.TextField(blank=True)
    prazo_entrega_dias = models.PositiveIntegerField(null=True, blank=True)
    observacao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']
        constraints = [
            models.UniqueConstraint(
                fields=['fonte_online'],
                condition=~Q(fonte_online=''),
                name='fornecedor_fonte_online_unica',
            ),
        ]

    def __str__(self):
        return self.nome

    @property
    def cnpj_formatado(self):
        numeros = ''.join(ch for ch in self.documento if ch.isdigit())
        if len(numeros) != 14:
            return self.documento
        return (
            f'{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/'
            f'{numeros[8:12]}-{numeros[12:]}'
        )

class PrecoFornecedorInsumo(models.Model):
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name='precos_fornecedores')
    fornecedor = models.ForeignKey(
        FornecedorInsumo,
        on_delete=models.PROTECT,
        related_name='precos',
    )
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=4)
    vigente_desde = models.DateField(default=timezone.localdate)
    vigente_ate = models.DateField(null=True, blank=True)
    ativo = models.BooleanField(default=True)
    observacao = models.TextField(blank=True)
    cadastrado_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='precos_insumos_cadastrados')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-vigente_desde', '-criado_em']
        indexes = [
            models.Index(fields=['insumo', 'ativo']),
            models.Index(fields=['fornecedor', 'ativo']),
            models.Index(fields=['vigente_desde']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(valor_unitario__gt=0),
                name='preco_insumo_valor_positivo',
            ),
        ]

    def clean(self):
        super().clean()
        if self.vigente_ate and self.vigente_ate < self.vigente_desde:
            raise ValidationError('A vigência final não pode ser anterior à vigência inicial.')

    def __str__(self):
        return f'{self.insumo} - {self.fornecedor}: {self.valor_unitario}'

class PesquisaPrecoOnline(models.Model):
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name='pesquisas_preco')
    termo = models.CharField(max_length=255)
    fonte = models.CharField(max_length=40, default='MERCADO_LIVRE')
    pesquisado_por = models.ForeignKey(User, on_delete=models.PROTECT)
    pesquisado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-pesquisado_em']

class OfertaPrecoOnline(models.Model):
    pesquisa = models.ForeignKey(
        PesquisaPrecoOnline,
        on_delete=models.CASCADE,
        related_name='ofertas',
    )
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, related_name='ofertas_online')
    fonte = models.CharField(max_length=40)
    codigo_externo = models.CharField(max_length=80)
    titulo = models.CharField(max_length=255)
    vendedor = models.CharField(max_length=160, blank=True)
    url = models.URLField(max_length=500)
    preco = models.DecimalField(max_digits=12, decimal_places=2)
    frete = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    preco_total = models.DecimalField(max_digits=12, decimal_places=2)
    frete_conhecido = models.BooleanField(default=False)
    condicao = models.CharField(max_length=30, blank=True)
    coletado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['preco_total', 'titulo']
        indexes = [
            models.Index(fields=['insumo', 'coletado_em']),
            models.Index(fields=['fonte', 'codigo_externo']),
        ]

class SolicitacaoInsumo(models.Model):

    STATUS = [
        ('PENDENTE', 'Pendente'),
        ('APROVADA', 'Aprovada'),
        ('REPROVADA', 'Reprovada'),
        ('EM_COMPRA', 'Em Compra'),
        ('FINALIZADA', 'Finalizada'),
    ]
    PRIORIDADE = [
        ('BAIXA', 'Baixa'),
        ('MEDIA', 'Média'),
        ('ALTA', 'Alta'),
        ('URGENTE', 'Urgente'),
    ]

    prioridade = models.CharField(max_length=10, choices=PRIORIDADE, default='MEDIA')
    protocolo = models.CharField(max_length=20, unique=True)
    base = models.ForeignKey('estoque.Base', on_delete=models.PROTECT)
    solicitante = models.ForeignKey(User, on_delete=models.PROTECT, related_name='solicitacoes_insumo')
    status = models.CharField(max_length=20, choices=STATUS, default='PENDENTE')
    aprovado_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='solicitacoes_aprovadas')
    aprovado_em = models.DateTimeField(null=True, blank=True)
    justificativa = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    observacao_aprovacao = models.TextField(blank=True)
    finalizado_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='solicitacoes_finalizadas')
    finalizado_em = models.DateTimeField(null=True, blank=True)
    em_compra_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='solicitacoes_em_compra')
    em_compra_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ('aprovar_solicitacao', 'Pode aprovar solicitações'),
            ('reprovar_solicitacao', 'Pode reprovar solicitações'),
            ('colocar_em_compra', 'Pode enviar solicitação para compras'),
            ('finalizar_solicitacao', 'Pode finalizar solicitações'),
        ]

class ItemSolicitacaoInsumo(models.Model):

    solicitacao = models.ForeignKey(SolicitacaoInsumo, on_delete=models.CASCADE, related_name='itens')
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    quantidade_atendida = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observacao = models.TextField(blank=True)

class MovimentacaoInsumo(models.Model):
    TIPOS = [
        ('ENTRADA', 'Entrada'),
        ('SAIDA', 'Saída'),
        ('DEVOLUCAO', 'Devolução'),
        ('AJUSTE_ENTRADA', 'Ajuste Entrada'),
        ('AJUSTE_SAIDA', 'Ajuste Saída'),
        ('PERDA', 'Perda'),
    ]

    base = models.ForeignKey('estoque.Base', on_delete=models.PROTECT)
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    solicitacao = models.ForeignKey(SolicitacaoInsumo, null=True, blank=True, on_delete=models.SET_NULL)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['base', 'insumo']),
            models.Index(fields=['tipo']),
            models.Index(fields=['criado_em']),
        ]

        permissions = [
            ('realizar_entrada', 'Pode registrar entradas'),
            ('realizar_saida', 'Pode registrar saídas'),
            ('realizar_devolucao', 'Pode registrar devoluções'),
            ('realizar_perda', 'Pode registrar perdas'),
            ('realizar_ajuste', 'Pode realizar ajustes'),
            ('visualizar_valores_estoque', 'Pode visualizar valores do estoque'),
            ('gerenciar_fornecedores', 'Pode gerenciar fornecedores'),
            ('gerenciar_precos', 'Pode gerenciar preços'),
            ('gerenciar_aquisicoes', 'Pode gerenciar aquisições'),
            ('criar_remessa_compra', 'Pode criar remessa de compra'),
            ('confirmar_remessa_compra', 'Pode confirmar remessa de compra'),
        ]


class SaldoInsumoBase(models.Model):
    base = models.ForeignKey(
        'estoque.Base',
        on_delete=models.PROTECT,
        related_name='saldos_insumos',
    )
    insumo = models.ForeignKey(
        Insumo,
        on_delete=models.PROTECT,
        related_name='saldos_por_base',
    )
    saldo = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    saldo_reservado = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    custo_medio = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    ultima_entrada_em = models.DateTimeField(null=True, blank=True)
    recalculado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['base__nome', 'insumo__descricao']
        constraints = [
            models.UniqueConstraint(
                fields=['base', 'insumo'],
                name='saldo_insumo_base_unico',
            ),
            models.CheckConstraint(
                condition=Q(saldo__gte=0),
                name='saldo_insumo_base_nao_negativo',
            ),
            models.CheckConstraint(
                condition=Q(custo_medio__gte=0),
                name='custo_medio_insumo_base_nao_negativo',
            ),
            models.CheckConstraint(
                condition=Q(saldo_reservado__gte=0),
                name='saldo_insumo_reservado_nao_negativo',
            ),
            models.CheckConstraint(
                condition=Q(saldo_reservado__lte=F('saldo')),
                name='saldo_insumo_reservado_ate_saldo',
            ),
        ]
        indexes = [
            models.Index(fields=['base', 'saldo']),
            models.Index(fields=['insumo', 'saldo']),
        ]

    @property
    def valor_total(self):
        return self.saldo * self.custo_medio

    @property
    def saldo_disponivel(self):
        return self.saldo - self.saldo_reservado

    def __str__(self):
        return f'{self.base} - {self.insumo}: {self.saldo}'


class HistoricoCadastroInsumo(models.Model):
    insumo = models.ForeignKey(
        Insumo, on_delete=models.PROTECT, related_name='historico_cadastro'
    )
    campo = models.CharField(max_length=60, db_index=True)
    valor_anterior = models.TextField(blank=True)
    valor_novo = models.TextField(blank=True)
    motivo = models.TextField()
    origem = models.CharField(max_length=80, blank=True, db_index=True)
    alterado_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT,
        related_name='alteracoes_cadastro_insumo',
    )
    alterado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-alterado_em', '-id']

class Cliente(models.Model):

    sigla = models.CharField(max_length=10, unique=True)
    nome = models.CharField(max_length=200)
    ativo = models.BooleanField(default=True)
    status_relatorio = models.CharField(max_length=20, blank=True, default='')

    def __str__(self):
        return f'{self.sigla} - {self.nome}'

class Inventario(models.Model):

    STATUS = [
        ('PLANEJADO', 'Planejado'),
        ('EM_ANDAMENTO', 'Em andamento'),
        ('FINALIZADO', 'Finalizado'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='inventarios',)
    loja = models.CharField(max_length=50, db_index=True,)
    base = models.ForeignKey(Base, on_delete=models.PROTECT)
    data_inicio = models.DateField(db_index=True)
    data_fim = models.DateField(null=True, blank=True)
    inicio_previsto = models.DateTimeField(null=True, blank=True, db_index=True)
    fim_previsto = models.DateTimeField(null=True, blank=True)
    inicio_real = models.DateTimeField(null=True, blank=True, db_index=True)
    fim_real = models.DateTimeField(null=True, blank=True, db_index=True)
    inicio_contagem = models.DateTimeField(null=True, blank=True)
    fim_contagem = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='PLANEJADO')
    criado_por = models.ForeignKey(User, on_delete=models.PROTECT)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    cep = models.CharField(max_length=20, blank=True, null=True)
    cnpj = models.CharField(max_length=20, blank=True, null=True)
    dados_brutos = models.JSONField(default=dict, blank=True, null=True)
    tipo = models.CharField(max_length=20, blank=True, null=True)
    pessoas = models.IntegerField(blank=True, null=True)
    total_pecas = models.PositiveBigIntegerField(blank=True, null=True)
    custo_hora_pessoa = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )
    observacao = models.TextField(blank=True, null=True)
    lider = models.CharField(max_length=100, blank=True, null=True)
    lider_usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='inventarios_como_lider',
    )
    ponto_encontro = models.CharField(max_length=200, blank=True, null=True)
    horario_ponto = models.TimeField(blank=True, null=True)
    horario_inicio = models.TimeField(blank=True, null=True)
    tipo_visita = models.CharField(max_length=50, blank=True, null=True)
    responsavel_visita = models.CharField(max_length=100, blank=True, null=True)
    data_visita = models.DateField(blank=True, null=True)
    horario_visita = models.TimeField(blank=True, null=True)
    relatorio_visita = models.CharField(max_length=50, blank=True, null=True)
    prep = models.FloatField(blank=True, null=True)
    historico_equipe = models.CharField(max_length=50, blank=True, null=True)
    historico_pecas = models.CharField(max_length=50, blank=True, null=True)
    historico_satisfacao = models.CharField(max_length=50, blank=True, null=True)
    historico_preparacao = models.CharField(max_length=50, blank=True, null=True)
    historico_lider = models.CharField(max_length=100, blank=True, null=True)
    historico_data = models.DateField(blank=True, null=True)
    equipe_plan = models.IntegerField(blank=True, null=True)
    previsao_pecas = models.IntegerField(blank=True, null=True)
    prod_media = models.FloatField(blank=True, null=True)
    bid = models.CharField(max_length=10, blank=True, null=True)
    envio_escala = models.DateField(blank=True, null=True)
    chave = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):

        return (
            f'{self.cliente.sigla} '
            f'- Loja {self.loja}'
        )

    def clean(self):
        super().clean()
        erros = {}
        pares = (
            ('inicio_previsto', 'fim_previsto', 'O fim previsto não pode ser anterior ao início previsto.'),
            ('inicio_real', 'fim_real', 'O fim real não pode ser anterior ao início real.'),
            ('inicio_contagem', 'fim_contagem', 'O fim da contagem não pode ser anterior ao início da contagem.'),
        )
        for campo_inicio, campo_fim, mensagem in pares:
            inicio = getattr(self, campo_inicio)
            fim = getattr(self, campo_fim)
            if inicio and fim and fim < inicio:
                erros[campo_fim] = mensagem

        if self.inicio_real and self.inicio_contagem and self.inicio_contagem < self.inicio_real:
            erros['inicio_contagem'] = 'A contagem não pode começar antes do início real do inventário.'
        if self.fim_real and self.fim_contagem and self.fim_contagem > self.fim_real:
            erros['fim_contagem'] = 'A contagem não pode terminar depois do fim real do inventário.'
        if self.pessoas is not None and self.pessoas < 0:
            erros['pessoas'] = 'A quantidade de pessoas não pode ser negativa.'
        if self.custo_hora_pessoa is not None and self.custo_hora_pessoa < 0:
            erros['custo_hora_pessoa'] = 'O custo por pessoa/hora não pode ser negativo.'
        if erros:
            raise ValidationError(erros)

    @staticmethod
    def _duracao_horas(inicio, fim):
        if not inicio or not fim or fim < inicio:
            return None
        return (fim - inicio).total_seconds() / 3600

    @property
    def duracao_prevista_horas(self):
        return self._duracao_horas(self.inicio_previsto, self.fim_previsto)

    @property
    def duracao_total_horas(self):
        return self._duracao_horas(self.inicio_real, self.fim_real)

    @property
    def duracao_contagem_horas(self):
        return self._duracao_horas(self.inicio_contagem, self.fim_contagem)

    @property
    def tempo_improdutivo_horas(self):
        total = self.duracao_total_horas
        contagem = self.duracao_contagem_horas
        if total is None or contagem is None:
            return None
        return max(total - contagem, 0)

    @property
    def atraso_inicio_minutos(self):
        if not self.inicio_previsto or not self.inicio_real:
            return None
        return (self.inicio_real - self.inicio_previsto).total_seconds() / 60

    @property
    def desvio_fim_minutos(self):
        if not self.fim_previsto or not self.fim_real:
            return None
        return (self.fim_real - self.fim_previsto).total_seconds() / 60

    @property
    def pecas_por_pessoa(self):
        if self.total_pecas is None or not self.pessoas:
            return None
        return self.total_pecas / self.pessoas

    @property
    def produtividade_pessoa_hora(self):
        duracao = self.duracao_total_horas
        if self.total_pecas is None or not self.pessoas or not duracao:
            return None
        return self.total_pecas / self.pessoas / duracao

    @property
    def produtividade_contagem_pessoa_hora(self):
        duracao = self.duracao_contagem_horas
        if self.total_pecas is None or not self.pessoas or not duracao:
            return None
        return self.total_pecas / self.pessoas / duracao

    @property
    def custo_adicional_atraso(self):
        if (
            self.desvio_fim_minutos is None or
            self.desvio_fim_minutos <= 0 or
            not self.pessoas or
            self.custo_hora_pessoa is None
        ):
            return None
        return (
            self.custo_hora_pessoa *
            Decimal(self.pessoas) *
            Decimal(str(self.desvio_fim_minutos)) /
            Decimal(60)
        )

    class Meta:
        indexes = [
            models.Index(fields=['base', 'data_inicio'], name='insumos_inv_base_da_6b2e3f_idx'),
            models.Index(fields=['status', 'data_inicio'], name='insumos_inv_status__25ed2c_idx'),
        ]
        permissions = [
            ('gerenciar_inventarios', 'Pode gerenciar inventários'),
        ]

class AlteracaoCalendario(models.Model):
    ORIGEM_CHOICES = [
        ('ATUAL', 'Atual'),
        ('HISTORICO', 'Historico'),
    ]

    revisao = models.IntegerField(null=True, blank=True)
    data = models.DateField(null=True, blank=True)
    cliente = models.ForeignKey(Cliente, null=True, blank=True, on_delete=models.SET_NULL, related_name='alteracoes_calendario')
    cliente_sigla = models.CharField(max_length=20, db_index=True)
    loja = models.CharField(max_length=50, db_index=True)
    descricao = models.TextField(blank=True)
    regional_nome = models.CharField(max_length=100, blank=True)
    base = models.ForeignKey(Base, null=True, blank=True, on_delete=models.SET_NULL, related_name='alteracoes_calendario')
    solicitante = models.CharField(max_length=100, blank=True)
    observacao = models.TextField(blank=True)
    origem_bloco = models.CharField(max_length=20, choices=ORIGEM_CHOICES, default='ATUAL')
    arquivo = models.CharField(max_length=255, blank=True)
    importado_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='alteracoes_calendario_importadas')
    importado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Alteracao do calendario'
        verbose_name_plural = 'Alteracoes do calendario'
        indexes = [
            models.Index(fields=['data'], name='insumos_alt_data_b19931_idx'),
            models.Index(fields=['cliente_sigla', 'loja'], name='insumos_alt_cliente_163588_idx'),
            models.Index(fields=['origem_bloco', 'revisao'], name='insumos_alt_origem__a44284_idx'),
            models.Index(fields=['base', 'data'], name='insumos_alt_base_id_1b3c50_idx'),
        ]

    def __str__(self):
        return f'{self.cliente_sigla} - Loja {self.loja} | Rev {self.revisao or "-"}'

class ChecklistDiario(models.Model):
    STATUS = [
        ('ABERTO', 'Aberto'),
        ('EM_EXECUCAO', 'Em execução'),
        ('FINALIZADO', 'Finalizado'),
    ]

    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE, related_name='checklists')
    data_inicio = models.DateTimeField()
    data_fim = models.DateTimeField(null=True, blank=True)
    criado_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='checklists_criados')
    status = models.CharField(max_length=20, choices=STATUS, default='ABERTO')
    responsavel = models.ForeignKey(User, on_delete=models.PROTECT)
    observacao = models.TextField(blank=True)
    quantidade_volumes = models.PositiveIntegerField(default=0)
    transporte = models.CharField(max_length=200, blank=True)
    declaracao_quantidades = models.JSONField(default=dict, blank=True)
    declaracao_dados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
#   finalizado = models.BooleanField(default=False)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    finalizado_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='checklists_finalizados')

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['data_inicio']),
        ]

        permissions = [
            ('visualizar_checklists', 'Pode visualizar checklists'),
            ('gerenciar_checklists', 'Pode gerenciar checklists'),
            ('preencher_checklists', 'Pode preencher checklists'),
            ('finalizar_checklists', 'Pode finalizar checklists'),
            ('reabrir_checklists', 'Pode reabrir checklists'),
            ('imprimir_checklists', 'Pode imprimir checklists'),
            ('visualizar_historico_checklists', 'Pode visualizar históricos de checklists'),
        ]

class ItemChecklist(models.Model):
    STATUS_RETORNO = [
        ('PENDENTE', 'Pendente'),
        ('CONFERIDO', 'Conferido'),
    ]

    checklist = models.ForeignKey(ChecklistDiario, on_delete=models.CASCADE, related_name='itens')
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    quantidade_enviada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantidade_utilizada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantidade_retornada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantidade_perdida = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status_retorno = models.CharField(max_length=20, choices=STATUS_RETORNO, default='PENDENTE')

    class Meta:
        unique_together = (('checklist', 'insumo'),)

class ChecklistEquipamento(models.Model):
    STATUS_RETORNO = [
        ('PENDENTE', 'Pendente'),
        ('RETORNADO', 'Retornado'),
        ('SICK', 'SICK'),
        ('DANO', 'Dano'),
        ('PERDA', 'Perda'),
        ('ROUBO', 'Roubo'),
    ]

    checklist = models.ForeignKey('ChecklistDiario', on_delete=models.CASCADE, related_name='equipamentos_utilizados')
    equipamento = models.ForeignKey('estoque.Equipamento', on_delete=models.PROTECT)
    tag_saida = models.CharField(max_length=100, verbose_name="Nº Tag na Saída")
    tag_volta = models.CharField(max_length=100, null=True, blank=True, verbose_name="Nº Tag na Volta")
    data_retorno = models.DateTimeField(null=True, blank=True)
    status_retorno = models.CharField(max_length=20, choices=STATUS_RETORNO, default='PENDENTE')
    motivo_observacao = models.TextField(blank=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)
    resolvido_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='checklist_equipamentos_resolvidos')
    observacao = models.TextField(blank=True)

    class Meta:
        unique_together = (('checklist', 'equipamento'),)

    def __str__(self):
        return f"{self.equipamento} - {self.tag_saida}"


class ChecklistEquipamentoQuantidade(models.Model):
    CATEGORIAS = [
        ('Sistema', 'Sistema'),
        ('Coletores', 'Coletores'),
        ('Notebooks', 'Notebooks'),
        ('Impressoras', 'Impressoras'),
        ('Routers', 'Routers'),
    ]
    class StatusRetorno(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        CONFERIDO = 'CONFERIDO', 'Conferido'

    checklist = models.ForeignKey(
        ChecklistDiario,
        on_delete=models.CASCADE,
        related_name='equipamentos_quantitativos',
    )
    categoria = models.CharField(max_length=50, choices=CATEGORIAS)
    quantidade_enviada = models.PositiveIntegerField()
    quantidade_identificada = models.PositiveIntegerField(default=0)
    quantidade_retornada = models.PositiveIntegerField(default=0)
    status_retorno = models.CharField(
        max_length=20,
        choices=StatusRetorno.choices,
        default=StatusRetorno.PENDENTE,
    )
    conferido_por = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='checklists_equipamentos_conferidos',
    )
    conferido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['checklist', 'categoria'],
                name='checklist_categoria_equipamento_unica',
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade_identificada__lte=models.F('quantidade_enviada')),
                name='checklist_equip_identificados_lte_enviados',
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade_retornada__lte=models.F('quantidade_enviada')),
                name='checklist_equip_retornados_lte_enviados',
            ),
        ]

    @property
    def quantidade_nao_identificada(self):
        return self.quantidade_enviada - self.quantidade_identificada

    @property
    def quantidade_divergente(self):
        return self.quantidade_enviada - self.quantidade_retornada

    def __str__(self):
        return f'Checklist #{self.checklist_id} · {self.categoria}: {self.quantidade_enviada}'

class ChecklistLoteTag(models.Model):
    checklist = models.ForeignKey('ChecklistDiario', on_delete=models.CASCADE, related_name='lotes_tags_movimentados')
    lote = models.ForeignKey('LoteTag', on_delete=models.PROTECT, related_name='checklists_utilizados')
    rolo = models.ForeignKey('RoloTag', on_delete=models.PROTECT, null=True, blank=True, related_name='checklists_utilizados')
    numero_inicial_utilizado = models.IntegerField()
    numero_final_utilizado = models.IntegerField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Lote de TAG do checklist'
        verbose_name_plural = 'Lotes de TAG do checklist'
        indexes = [
            models.Index(fields=['checklist']),
            models.Index(fields=['lote']),
        ]

    def __str__(self):
        faixa = f'{self.lote.numero_inicial}-{self.lote.numero_final}'
        return f'Checklist #{self.checklist_id} | Lote {faixa} | início {self.numero_inicial_utilizado}'

    @property
    def quantidade_utilizada(self):
        if (
            self.numero_final_utilizado is not None and
            self.numero_final_utilizado >= self.numero_inicial_utilizado
        ):
            return self.numero_final_utilizado - self.numero_inicial_utilizado + 1
        return 0

    def validar_numero_inicial(self):
        if self.numero_inicial_utilizado < self.lote.numero_inicial or self.numero_inicial_utilizado > self.lote.numero_final:
            raise ValidationError(
                f'O número inicial {self.numero_inicial_utilizado} está fora da faixa do lote '
                f'({self.lote.numero_inicial} até {self.lote.numero_final}).'
            )

    def validar_numero_final(self):
        if self.numero_final_utilizado is None:
            return

        if self.numero_final_utilizado < self.numero_inicial_utilizado:
            raise ValidationError(
                'O número final utilizado não pode ser menor que o número inicial utilizado.'
            )

        if self.numero_final_utilizado < self.lote.numero_inicial or self.numero_final_utilizado > self.lote.numero_final:
            raise ValidationError(
                f'O número final {self.numero_final_utilizado} está fora da faixa do lote '
                f'({self.lote.numero_inicial} até {self.lote.numero_final}).'
            )

    def clean(self):
        super().clean()
        if self.lote_id:
            self.validar_numero_inicial()
            self.validar_numero_final()

class ConsumoInsumo(models.Model):

    indexes = [
        models.Index(fields=['inventario']),
        models.Index(fields=['insumo']),
        models.Index(fields=['criado_em']),
        models.Index(fields=['valor_total']),
    ]

    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE)
    item_checklist = models.ForeignKey(ItemChecklist, on_delete=models.PROTECT)
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['inventario']),
            models.Index(fields=['insumo']),
            models.Index(fields=['criado_em']),
        ]

        permissions = [
            ('visualizar_custos', 'Pode visualizar custos'),
            ('visualizar_dashboards_financeiros',
             'Pode visualizar dashboards financeiros'),
        ]

class HistoricoInsumo(models.Model):

    TIPO = [
        ('SOLICITACAO', 'Solicitação'),
        ('APROVACAO', 'Aprovação'),
        ('MOVIMENTACAO', 'Movimentação'),
        ('CHECKLIST', 'Checklist'),
        ('CONSUMO', 'Consumo'),
        ('PRECO', 'Preço'),
    ]

    tipo = models.CharField(max_length=30, choices=TIPO)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    descricao = models.TextField()
    dados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['tipo']),
            models.Index(fields=['criado_em']),
        ]

class LoteTag(models.Model):

    base = models.ForeignKey(Base, on_delete=models.PROTECT)
    numero_inicial = models.IntegerField()
    numero_final = models.IntegerField()
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    ativo = models.BooleanField(default=True)
    quantidade_total = models.IntegerField(default=0, editable=False)
    quantidade_disponivel = models.IntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['base']),
            models.Index(fields=['ativo']),
        ]
        permissions = [
            ('gerenciar_tags', 'Pode gerenciar TAGs'),
        ]

    def __str__(self):
        return f'Lote {self.numero_inicial}-{self.numero_final} | Base: {self.base.nome}'

    @property
    def faixa_label(self):
        return f'{self.numero_inicial} até {self.numero_final}'

    @property
    def tamanho_faixa(self):
        return self.numero_final - self.numero_inicial + 1

    def save(self, *args, **kwargs):
        self.quantidade_total = self.tamanho_faixa

        super().save(*args, **kwargs)

class RoloTag(models.Model):

    STATUS = [
        ('DISPONIVEL', 'Disponível'),
        ('EM_USO', 'Em uso'),
        ('ESGOTADO', 'Esgotado'),
    ]

    lote = models.ForeignKey(LoteTag, on_delete=models.CASCADE, related_name='rolos')
    codigo = models.PositiveIntegerField()
    numero_atual = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS, default='DISPONIVEL')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('lote', 'codigo'),)
        indexes = [
            models.Index(fields=['status'], name='insumos_rol_status_f17a57_idx'),
            models.Index(fields=['lote', 'status'], name='insumos_rol_lote_id_d5c504_idx'),
        ]

    def __str__(self):
        return f'Rolo {self.codigo} | {self.lote.faixa_label} | atual {self.numero_atual}'

    def clean(self):
        super().clean()
        if self.lote_id and (
            self.numero_atual < self.lote.numero_inicial or
            self.numero_atual > self.lote.numero_final
        ):
            raise ValidationError(
                f'O número atual {self.numero_atual} está fora da faixa do lote '
                f'({self.lote.numero_inicial} até {self.lote.numero_final}).'
            )

class MovimentacaoTag(models.Model):
    TIPOS = [
        ('UTILIZACAO', 'Utilização em inventário'),
        ('PERDA', 'Perda'),
        ('AJUSTE', 'Ajuste'),
    ]

    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE)
    lote = models.ForeignKey(LoteTag, on_delete=models.PROTECT)
    numero_inicial = models.IntegerField()
    numero_final = models.IntegerField()
    tipo = models.CharField(max_length=20, choices=TIPOS)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    criado_em = models.DateTimeField(auto_now_add=True)

