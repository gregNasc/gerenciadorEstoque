from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _


# ---------------- BASE ----------------
class Empresa(models.Model):
    nome = models.CharField(max_length=200)

    def __str__(self):
        return self.nome

class Base(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="bases"
    )
    nome = models.CharField(max_length=100)

    grupo_regional = models.ForeignKey(
        'GrupoRegional',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='bases'
    )

    def __str__(self):
        return f"{self.nome} ({self.empresa.nome})"

class Perfil(models.Model):

    class Idioma(models.TextChoices):
        PT_BR = "pt-br", "Português"
        ES = "es", "Español"

    idioma = models.CharField(
        max_length=10,
        choices=Idioma.choices,
        default=Idioma.PT_BR
    )

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        GESTOR = "gestor", "Gestor"
        OPERADOR = "operador", "Operador"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil")

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="perfis"
    )

    regionais = models.ManyToManyField(
        Base,
        blank=True,
        related_name="perfis"
    )

    role = models.CharField(max_length=10, choices=Role.choices)

    # -------- REGIONAIS --------
    @property
    def regionais_ids(self):
        return list(self.regionais.values_list('id', flat=True))

    @property
    def regionais_ativas(self):
        return self.regionais.all()

    # -------- ROLES --------
    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_gestor(self):
        return self.role == self.Role.GESTOR

    @property
    def is_operador(self):
        return self.role == self.Role.OPERADOR

    # -------- SAVE --------
    def save(self, *args, **kwargs):

        if self.is_admin:
            self.empresa = None

        super().save(*args, **kwargs)

        if self.is_admin:
            self.regionais.clear()

    # -------- PERMISSÕES --------
    @property
    def pode_ver_tudo(self):
        return self.is_admin

    @property
    def pode_transferir(self):
        return self.is_admin or self.is_gestor

    @property
    def pode_receber(self):
        return self.is_admin or self.is_gestor

    @property
    def pode_aprovar(self):
        return self.is_admin

    @property
    def pode_marcar_sick(self):
        return self.is_admin or self.is_gestor or self.is_operador

class GrupoRegional(models.Model):

    nome = models.CharField(
        max_length=100,
        unique=True
    )

    gestor_principal = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='grupos_regionais'
    )

    ativo = models.BooleanField(default=True)

    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome

# ---------------- PRODUTO ----------------
class Produto(models.Model):

    CATEGORIAS = [
        ('Coletores', _('Coletores')),
        ('Impressoras', _('Impressoras')),
        ('Notebooks', _('Notebooks')),
        ('Routers', _('Routers')),
    ]

    codigo = models.CharField(max_length=50, unique=True)
    descricao = models.CharField(max_length=255)
    fabricante = models.CharField(max_length=100)
    modelo = models.CharField(max_length=100)

    categoria = models.CharField(max_length=50, choices=CATEGORIAS, db_index=True)

    def __str__(self):
        return self.descricao

# ---------------- EQUIPAMENTO ----------------
class Equipamento(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['regional']),
            models.Index(fields=['data_cadastro']),
        ]
    STATUS_CHOICES = [
        ('ATIVO', _('Ativo')),
        ('TRANSFERENCIA', _('Em Transferência')),
        ('MANUTENCAO', _('Manutenção')),
        ('SICK', _('Sick')),
        ('BAIXA', _('Baixa')),
    ]

    produto = models.ForeignKey(Produto, null=True, on_delete=models.SET_NULL)
    numero_serie = models.CharField(max_length=100, unique=True)
    patrimonio = models.CharField(max_length=100, unique=True)
    regional = models.ForeignKey(Base, on_delete=models.PROTECT)
    responsavel = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ATIVO')
    data_aquisicao = models.DateField(auto_now_add=True)
    foto = models.ImageField(upload_to='equipamentos/', null=True, blank=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)
    codigo = models.CharField(max_length=50, unique=True)
    qr_code = models.ImageField(upload_to="qrcodes/", null=True, blank=True)

    def __str__(self):
        return f"{self.numero_serie} - {self.produto.descricao}"

    def save(self, *args, **kwargs):
        if not self.codigo:
            ultimo = Equipamento.objects.order_by('-id').first()
            proximo = (ultimo.id + 1) if ultimo else 1
            self.codigo = f"EQP-{proximo:06d}"
        super().save(*args, **kwargs)

# ---------------- TRANSFERENCIA ----------------
class Solicitacao(models.Model):
    STATUS = [
        ('PENDENTE', _('Pendente')),
        ('APROVADO', _('Aprovado')),
        ('REJEITADO', _('Rejeitado')),
        ('EM_TRANSFERENCIA', _('Em Transferência')),
        ('FINALIZADO', _('Finalizado')),
    ]

    #produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    #quantidade = models.IntegerField()
    motivo = models.TextField()

    regional_solicitante = models.ForeignKey(Base, on_delete=models.CASCADE)

    status = models.CharField(max_length=20, choices=STATUS, default='PENDENTE')

    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    aprovado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='aprovacoes'
    )

    regional_origem = models.ForeignKey(
        Base,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='origens'
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    data_aprovacao = models.DateTimeField(null=True, blank=True)

class SolicitacaoItem(models.Model):
    class Meta:
        db_table = 'estoque_itemsolicitacao'

    CATEGORIAS = [
        ('Coletores', _('Coletores')),
        ('Impressoras', _('Impressoras')),
        ('Notebooks', _('Notebooks')),
        ('Routers', _('Routers')),
    ]

    solicitacao = models.ForeignKey(
        'Solicitacao',
        on_delete=models.CASCADE,
        related_name='itens'
    )

    categoria = models.CharField(
        max_length=50,
        choices=CATEGORIAS,
        db_index=True
    )

    quantidade = models.PositiveIntegerField()
    atendido = models.PositiveIntegerField(
        default=0,
        db_column="quantidade_atendida",
        db_index=True
    )

    @property
    def pendente(self):
        return self.quantidade - self.atendido

class AlocacaoSolicitacaoItem(models.Model):
    item = models.ForeignKey(
        SolicitacaoItem,
        on_delete=models.CASCADE,
        related_name='alocacoes'
    )

    regional_origem = models.ForeignKey(
        'Base',
        on_delete=models.CASCADE
    )

    quantidade = models.PositiveIntegerField()

    criado_em = models.DateTimeField(auto_now_add=True)

class Transferencia(models.Model):
    STATUS = [
        ('PENDENTE', _('Pendente')),
        ('EM_TRANSITO', _('Em trânsito')),
        ('CONCLUIDA', _('Concluída')),
        ('CANCELADA', _('Cancelada')),
    ]

#    equipamento = models.ForeignKey(Equipamento, null=True, blank=True, on_delete=models.SET_NULL)

    alocacao = models.ForeignKey(AlocacaoSolicitacaoItem,on_delete=models.SET_NULL, null=True, blank=True)

    solicitado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    regional_origem = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='origem')
    regional_destino = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='destino')

    status = models.CharField(max_length=20, choices=STATUS, default='PENDENTE')

    data_criacao = models.DateTimeField(auto_now_add=True)
    data_envio = models.DateTimeField(null=True, blank=True)
    data_recebimento = models.DateTimeField(null=True, blank=True)

    def enviar(self):
        if self.status != 'PENDENTE':
            raise ValueError("Só pode enviar se estiver pendente")

        self.status = 'EM_TRANSITO'
        self.data_envio = timezone.now()
        self.save()

        usuarios = User.objects.filter(
            perfil__regionais=self.regional_destino
        )

        for user in usuarios:
            Notificacao.objects.get_or_create(
                usuario=user,
                transferencia=self,
                tipo='TRANSFERENCIA',
                evento='EM_TRANSFERENCIA',
                defaults={
                    'mensagem': f"Nova transferência recebida de {self.regional_origem.nome}",
                    'link': f"/transferencias/{self.id}/"
                }
            )

    def receber(self):
        if self.status != 'ENVIADO':
            raise ValueError("Só pode receber se estiver enviado")

        self.status = 'RECEBIDO'
        self.data_recebimento = timezone.now()
        self.save()

class TransferenciaItem(models.Model):

    transferencia = models.ForeignKey(
        Transferencia,
        on_delete=models.CASCADE,
        related_name='itens'
    )

    equipamento = models.ForeignKey(
        Equipamento,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    status = models.CharField(max_length=20, default='SELECIONADO')

class Notificacao(models.Model):

    TIPOS = [
        ('SOLICITACAO', _('Solicitação')),
        ('TRANSFERENCIA', _('Transferência')),
    ]

    EVENTOS = [
        ('CRIADA', _('Criada')),
        ('APROVADA', _('Aprovada')),
        ('REJEITADA', _('Rejeitada')),
        ('EM_TRANSFERENCIA', _('Em transferência')),
        ('RECEBIDA', _('Recebida')),
    ]

    transferencia = models.ForeignKey(
        Transferencia,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    solicitacao = models.ForeignKey(
        Solicitacao,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    tipo = models.CharField(max_length=20, choices=TIPOS)
    evento = models.CharField(max_length=30, choices=EVENTOS)

    mensagem = models.CharField(max_length=255)

    lida = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    link = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['usuario', 'tipo', 'evento', 'transferencia', 'solicitacao'],
                name='unique_notificacao_evento_transferencia'
            )
        ]

    def save(self, *args, **kwargs):
        if self.transferencia:
            existente = Notificacao.objects.filter(
                usuario=self.usuario,
                tipo=self.tipo,
                evento=self.evento,
                transferencia=self.transferencia
            ).first()

            if existente:
                return existente

        super().save(*args, **kwargs)

class PedidoTransferencia(models.Model):

    solicitacao = models.ForeignKey(Solicitacao, on_delete=models.CASCADE)

    regional_origem = models.ForeignKey(
        Base,
        on_delete=models.CASCADE,
        related_name='pedidos_origem'
    )

    regional_destino = models.ForeignKey(
        Base,
        on_delete=models.CASCADE,
        related_name='pedidos_destino'
    )

    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    status = models.CharField(max_length=20, default='ABERTO')

class PedidoItem(models.Model):

    pedido = models.ForeignKey(PedidoTransferencia, related_name='itens', on_delete=models.CASCADE)

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.IntegerField()

# ---------------- SICK ----------------
class StatusEquipamento(models.TextChoices):
    ATIVO = 'ATIVO', _('Ativo')
    SICK = 'SICK', _('SICK')
    MANUTENCAO = 'MANUTENCAO', _('Manutenção')
    SUCATA= 'SUCATA', _('Sucata')
    INATIVO = 'INATIVO', _('Inativo')

class Sick(models.Model):
    equipamento = models.ForeignKey(Equipamento, on_delete=models.CASCADE, related_name='sicks')
    categoria = models.CharField(max_length=100)
    motivo = models.TextField(blank=True, null=True)
    previsao_retorno = models.DateField(null=True, blank=True)
    data_ocorrencia = models.DateTimeField(auto_now_add=True, db_index=True)
    data_resolucao = models.DateTimeField(null=True, blank=True)
    resolvido_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    ativo = models.BooleanField(default=True, db_index=True)
    descricao = models.TextField(null=True, blank=True)

    status_final = models.CharField(max_length=20, choices=StatusEquipamento.choices, null=True, blank=True)
    observacao_resolucao = models.TextField(null=True, blank=True)

# ---------------- HISTORICO ----------------
class Historico(models.Model):
    TIPO_ACOES = [
        ('CRIACAO', _('Criação')),
        ('TRANSFERENCIA', _('Transferência')),
        ('STATUS', _('Mudança de Status')),
        ('EDICAO', _('Edição')),
    ]

    equipamento = models.ForeignKey(Equipamento, on_delete=models.CASCADE)
    tipo_acao = models.CharField(max_length=50, choices=TIPO_ACOES)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT)
    detalhes = models.JSONField(blank=True, null=True)
    data = models.DateTimeField(auto_now_add=True, db_index=True)

# ---------------- DESCRICAO ----------------
class Descricao(models.Model):
    descricao = models.CharField(max_length=255)

    def __str__(self):
        return self.descricao

# ---------------- ALERTA ----------------
class Alerta(models.Model):
    tipo = models.CharField(max_length=50)
    mensagem = models.TextField()
    resolvido = models.BooleanField(default=False)

@receiver([post_save, post_delete], sender=Equipamento)
def limpar_cache_estoque(sender, instance, **kwargs):
    cache_keys = [
        'views.decorators.cache.cache_page.*',
        f'estoque_regional_{instance.regional_id}',
        'estoque_kpis_gerais',
    ]
    for key in cache_keys:
        cache.delete(key)
