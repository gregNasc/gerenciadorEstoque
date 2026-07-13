from django.db import models
from estoque.models import Base
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
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
    estoque_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estoque_maximo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return self.descricao


class FornecedorInsumo(models.Model):
    nome = models.CharField(max_length=160, unique=True)
    documento = models.CharField(max_length=30, unique=True, db_index=True)
    contato = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    prazo_entrega_dias = models.PositiveIntegerField(null=True, blank=True)
    observacao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']

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
        ]

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
    observacao = models.TextField(blank=True, null=True)
    lider = models.CharField(max_length=100, blank=True, null=True)
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
            ('gerenciar_checklists', 'Pode gerenciar checklists'),
            ('finalizar_checklists', 'Pode finalizar checklists'),
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

