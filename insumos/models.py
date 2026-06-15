from django.db import models
from estoque.models import Base
from django.contrib.auth.models import User
from django.conf import settings

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
    estoque_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    valor_medio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estoque_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estoque_maximo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return self.descricao

class SolicitacaoInsumo(models.Model):

    STATUS = [
        ('PENDENTE', 'Pendente'),
        ('APROVADA', 'Aprovada'),
        ('REPROVADA', 'Reprovada'),
        ('EM_COMPRA', 'Em Compra'),
        ('FINALIZADA', 'Finalizada'),
    ]

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

class ItemSolicitacaoInsumo(models.Model):

    solicitacao = models.ForeignKey(SolicitacaoInsumo, on_delete=models.CASCADE, related_name='itens')
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)

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

class Cliente(models.Model):

    sigla = models.CharField(max_length=10, unique=True)
    nome = models.CharField(max_length=200)
    ativo = models.BooleanField(default=True)

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
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='PLANEJADO')
    criado_por = models.ForeignKey(User, on_delete=models.PROTECT)

    def __str__(self):

        return (
            f'{self.cliente.sigla} '
            f'- Loja {self.loja}'
        )

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

class ItemChecklist(models.Model):

    checklist = models.ForeignKey(ChecklistDiario, on_delete=models.CASCADE, related_name='itens')
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    quantidade_enviada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantidade_utilizada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantidade_retornada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantidade_perdida = models.DecimalField(max_digits=10, decimal_places=2, default=0)

class ConsumoInsumo(models.Model):

    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE)
    item_checklist = models.ForeignKey(ItemChecklist, on_delete=models.PROTECT)
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2)
    criado_em = models.DateTimeField(auto_now_add=True)

class HistoricoInsumo(models.Model):

    TIPO = [
        ('SOLICITACAO', 'Solicitação'),
        ('APROVACAO', 'Aprovação'),
        ('MOVIMENTACAO', 'Movimentação'),
        ('CHECKLIST', 'Checklist'),
        ('CONSUMO', 'Consumo'),
    ]

    tipo = models.CharField(max_length=30, choices=TIPO)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    descricao = models.TextField()
    dados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

class LoteTag(models.Model):

    base = models.ForeignKey(Base, on_delete=models.PROTECT)
    numero_inicial = models.IntegerField()
    numero_final = models.IntegerField()
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    ativo = models.BooleanField(default=True)

class MovimentacaoTag(models.Model):

    TIPOS = [
        ('ENVIO', 'Envio'),
        ('RETORNO', 'Retorno'),
        ('PERDA', 'Perda'),
    ]

    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE)
    lote = models.ForeignKey(LoteTag, on_delete=models.PROTECT)
    numero_inicial = models.IntegerField()
    numero_final = models.IntegerField()
    tipo = models.CharField(max_length=20, choices=TIPOS)

