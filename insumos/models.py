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

class ItemSolicitacaoInsumo(models.Model):

    solicitacao = models.ForeignKey(SolicitacaoInsumo, on_delete=models.CASCADE, related_name='itens')
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)

class MovimentacaoInsumo(models.Model):

    TIPOS = [
        ('ENTRADA', 'Entrada'),
        ('SAIDA', 'Saída'),
        ('DEVOLUCAO', 'Devolução'),
        ('AJUSTE', 'Ajuste'),
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
