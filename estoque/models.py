from datetime import timedelta
import uuid
from urllib.parse import quote

from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from insumos.constants import GruposInsumos


def _url_rastreamento_correios(codigo):
    codigo = (codigo or '').strip()
    if not codigo:
        return ''
    return f'https://rastreamento.correios.com.br/app/index.php?objetos={quote(codigo)}'


# ---------------- BASE ----------------
class Empresa(models.Model):
    nome = models.CharField(max_length=200)

    def __str__(self):
        return self.nome

class Base(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="bases")
    nome = models.CharField(max_length=100)
    grupo_regional = models.ForeignKey('GrupoRegional', null=True, blank=True, on_delete=models.SET_NULL, related_name='bases')

    def __str__(self):
        return f"{self.nome} ({self.empresa.nome})"


class EnderecoPostalBase(models.Model):
    base = models.OneToOneField(
        Base,
        on_delete=models.CASCADE,
        related_name="endereco_postal",
    )
    nome_destinatario = models.CharField(max_length=150, blank=True)
    logradouro = models.CharField(max_length=180)
    numero = models.CharField(max_length=30)
    complemento = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    uf = models.CharField(max_length=2)
    cep = models.CharField(max_length=9)
    telefone = models.CharField(max_length=20, blank=True)
    responsavel = models.CharField(max_length=150, blank=True)
    documento = models.CharField(max_length=30, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.base.nome} - {self.cidade}/{self.uf}"

class Perfil(models.Model):

    class Idioma(models.TextChoices):
        PT_BR = "pt-br", "Português"
        ES = "es", "Español"
        EN = "en", "English"

    idioma = models.CharField(max_length=10, choices=Idioma.choices, default=Idioma.PT_BR)

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        GESTOR = "gestor", "Gestor"
        OPERADOR = "operador", "Operador"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="perfil")
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name="perfis")
    regionais = models.ManyToManyField(Base, blank=True, related_name="perfis")
    bases_checklist = models.ManyToManyField(Base, blank=True, related_name="perfis_checklist")
    empresas_escopo_compras = models.ManyToManyField(
        Empresa,
        blank=True,
        related_name='perfis_compras',
    )
    bases_escopo_compras = models.ManyToManyField(
        Base,
        blank=True,
        related_name='perfis_compras',
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    telefone = models.CharField(max_length=20, blank=True, default="")
    telefone_alternativo = models.CharField(max_length=20, blank=True, default="")
    whatsapp_numero = models.CharField(max_length=20, blank=True, default="")
    whatsapp_ativo = models.BooleanField(default=False)
    whatsapp_consentimento_em = models.DateTimeField(null=True, blank=True)
    whatsapp_consentimento_origem = models.CharField(max_length=100, blank=True)
    whatsapp_revogado_em = models.DateTimeField(null=True, blank=True)

    @property
    def grupos_insumos(self):

        return self.user.groups.filter(
            name__startswith='INSUMOS_'
        )

    @property
    def is_solicitante_insumos(self):
        return self.user.groups.filter(
            name=GruposInsumos.SOLICITANTE
        ).exists()

    @property
    def is_compras_insumos(self):
        return self.user.groups.filter(
            name=GruposInsumos.COMPRAS
        ).exists()

    @property
    def is_planejamento_insumos(self):
        return self.user.groups.filter(
            name=GruposInsumos.PLANEJAMENTO
        ).exists()

    @property
    def is_financeiro_insumos(self):
        return self.user.groups.filter(
            name=GruposInsumos.FINANCEIRO
        ).exists()

    @property
    def is_executivo_insumos(self):
        return self.user.groups.filter(
            name=GruposInsumos.EXECUTIVO
        ).exists()

    @property
    def is_funcional_global(self):
        return (
            self.is_compras_insumos or
            self.is_planejamento_insumos or
            self.is_financeiro_insumos or
            self.is_executivo_insumos
        )

    @property
    def pode_ver_empresas_globais(self):
        return self.is_admin or self.is_funcional_global

    # -------- REGIONAIS --------
    @property
    def regionais_ids(self):
        return list(self.regionais.values_list('id', flat=True))

    @property
    def regionais_ativas(self):
        return self.regionais.all()

    @property
    def bases_checklist_ativas(self):
        if self.bases_checklist.exists():
            return self.bases_checklist.all()
        return self.regionais.all()

    @property
    def bases_checklist_ids(self):
        if self.bases_checklist.exists():
            return list(self.bases_checklist.values_list('id', flat=True))
        return self.regionais_ids

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

    nome = models.CharField(max_length=100, unique=True)
    gestor_principal = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='grupos_regionais')
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Grupo Regional'
        verbose_name_plural = 'Grupos Regionais'
        ordering = ['nome']

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
    nome_resumido = models.CharField(max_length=120, blank=True)
    sku_fabricante = models.CharField(max_length=100, blank=True, db_index=True)
    subcategoria = models.CharField(max_length=100, blank=True)
    unidade_medida = models.CharField(max_length=20, default='UN')
    quantidade_embalagem = models.DecimalField(max_digits=12, decimal_places=4, default=1)
    especificacoes_tecnicas = models.JSONField(default=dict, blank=True)
    ativo = models.BooleanField(default=True, db_index=True)
    criado_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name='produtos_criados'
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.descricao

# ---------------- EQUIPAMENTO ----------------
class Equipamento(models.Model):
    class OrigemValor(models.TextChoices):
        DOCUMENTO_COMPRA = 'DOCUMENTO_COMPRA', _('Documento de compra')
        INFORMADO_COMPRAS = 'INFORMADO_COMPRAS', _('Informado por Compras')
        ESTIMATIVA_MERCADO = 'ESTIMATIVA_MERCADO', _('Estimativa de mercado')
        LEGADO_SEM_DOCUMENTO = 'LEGADO_SEM_DOCUMENTO', _('Legado sem documento')
        SEM_PRECO_VALIDADO = 'SEM_PRECO_VALIDADO', _('Sem preço validado')

    class CondicaoValor(models.TextChoices):
        NOVO = 'NOVO', _('Novo')
        USADO = 'USADO', _('Usado')
        RECONDICIONADO = 'RECONDICIONADO', _('Recondicionado')
    class Finalidade(models.TextChoices):
        OPERACIONAL = 'OPERACIONAL', _('Operacional')
        ADMINISTRATIVO = 'ADMINISTRATIVO', _('Administrativo')

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['regional']),
            models.Index(fields=['data_cadastro']),
        ]
    STATUS_CHOICES = [
        ('ATIVO', _('Ativo')),
        ('RESERVADO_TRANSFERENCIA', _('Reservado para Transferencia')),
        ('EM_TRANSITO', _('Em Transito')),
        ('MANUTENCAO', _('Manutencao')),
        ('SICK', _('Sick')),
        ('EM_USO', _('Em Uso')),
        ('EMPRESTADO', _('Emprestado')),
        ('BAIXA', _('Baixa')),
        ('INATIVO', _('Inativo')),
    ]

    produto = models.ForeignKey(Produto, null=True, on_delete=models.SET_NULL)
    numero_serie = models.CharField(max_length=100, unique=True)
    patrimonio = models.CharField(max_length=100, unique=True)
    regional = models.ForeignKey(Base, on_delete=models.PROTECT)
    responsavel = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default='ATIVO')
    finalidade = models.CharField(
        max_length=20,
        choices=Finalidade.choices,
        default=Finalidade.OPERACIONAL,
        db_index=True,
    )
    data_aquisicao = models.DateField(default=timezone.localdate)
    fornecedor = models.ForeignKey(
        'insumos.FornecedorInsumo', null=True, blank=True, on_delete=models.PROTECT,
        related_name='equipamentos_fornecidos',
    )
    custo_aquisicao = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    preco_referencia = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    origem_valor = models.CharField(
        max_length=30, choices=OrigemValor.choices, default=OrigemValor.SEM_PRECO_VALIDADO,
        db_index=True,
    )
    condicao_valor = models.CharField(
        max_length=20, choices=CondicaoValor.choices, default=CondicaoValor.NOVO,
    )
    documento_compra = models.CharField(max_length=120, blank=True)
    garantia_ate = models.DateField(null=True, blank=True)
    valor_validado_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT,
        related_name='equipamentos_valor_validado',
    )
    valor_validado_em = models.DateTimeField(null=True, blank=True)
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

# ---------------- EMPRÉSTIMO ----------------
class Emprestimo(models.Model):
    class Status(models.TextChoices):
        AGUARDANDO_RECEBIMENTO = 'AGUARDANDO_RECEBIMENTO', _('Aguardando recebimento')
        EMPRESTADO = 'EMPRESTADO', _('Emprestado')
        AGUARDANDO_DEVOLUCAO = (
            'AGUARDANDO_CONFIRMACAO_DEVOLUCAO',
            _('Aguardando confirmação da devolução'),
        )
        FINALIZADO = 'FINALIZADO', _('Finalizado')
        CANCELADO = 'CANCELADO', _('Cancelado')

    STATUS = Status.choices

    protocolo = models.CharField(max_length=20, unique=True)
    grupo = models.ForeignKey(GrupoRegional, on_delete=models.PROTECT)
    regional_origem = models.ForeignKey(Base, related_name='emprestimos_saida', on_delete=models.PROTECT)
    regional_destino = models.ForeignKey(Base, related_name='emprestimos_entrada', on_delete=models.PROTECT)
    solicitado_por = models.ForeignKey(User, on_delete=models.PROTECT)
    aprovado_por = models.ForeignKey(User, null=True, blank=True, related_name='emprestimos_aprovados', on_delete=models.SET_NULL)
    motivo = models.TextField()
    data_emprestimo = models.DateField()
    data_prevista_devolucao = models.DateField()
    data_devolucao = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=35,
        choices=Status.choices,
        default=Status.AGUARDANDO_RECEBIMENTO,
    )
    confirmado_recebimento = models.BooleanField(default=False)
    confirmado_devolucao = models.BooleanField(default=False)
    codigo_rastreio_envio = models.CharField(max_length=100, blank=True)
    codigo_rastreio_devolucao = models.CharField(max_length=100, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    @property
    def url_rastreio_envio(self):
        return _url_rastreamento_correios(self.codigo_rastreio_envio)

    @property
    def url_rastreio_devolucao(self):
        return _url_rastreamento_correios(self.codigo_rastreio_devolucao)

    @property
    def esta_atrasado(self):
        return (
                self.status not in ['FINALIZADO', 'CANCELADO']
                and self.data_prevista_devolucao
                and timezone.localdate() > self.data_prevista_devolucao
        )

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return self.protocolo

class ItemEmprestimo(models.Model):
    class Status(models.TextChoices):
        RESERVADO = 'RESERVADO', _('Reservado')
        ENVIADO = 'ENVIADO', _('Enviado')
        RECEBIDO = 'RECEBIDO', _('Recebido')
        DEVOLVIDO = 'DEVOLVIDO', _('Devolvido')
        DIVERGENCIA = 'DIVERGENCIA', _('Divergência')

    STATUS = Status.choices

    emprestimo = models.ForeignKey(Emprestimo, related_name='itens', on_delete=models.CASCADE)
    equipamento = models.ForeignKey(Equipamento, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RESERVADO,
    )
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    quantidade = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f'{self.emprestimo} - {self.equipamento}'

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
    status = models.CharField(max_length=40, choices=STATUS, default='PENDENTE')
    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    aprovado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='aprovacoes')
    regional_origem = models.ForeignKey(Base, null=True, blank=True, on_delete=models.SET_NULL, related_name='origens')
    criado_em = models.DateTimeField(auto_now_add=True)
    data_aprovacao = models.DateTimeField(null=True, blank=True)
    motivo_recusa = models.TextField(blank=True, null=True)
    recusado_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='recusas_solicitacao')
    data_recusa = models.DateTimeField(null=True, blank=True)

class SolicitacaoItem(models.Model):
    class Meta:
        db_table = 'estoque_itemsolicitacao'

    CATEGORIAS = [
        ('Coletores', _('Coletores')),
        ('Impressoras', _('Impressoras')),
        ('Notebooks', _('Notebooks')),
        ('Routers', _('Routers')),
    ]

    solicitacao = models.ForeignKey('Solicitacao', on_delete=models.CASCADE, related_name='itens')
    categoria = models.CharField(max_length=50, choices=CATEGORIAS, db_index=True)
    quantidade = models.PositiveIntegerField()
    atendido = models.PositiveIntegerField(default=0, db_column="quantidade_atendida", db_index=True)

    @property
    def pendente(self):
        return self.quantidade - self.atendido

class AlocacaoSolicitacaoItem(models.Model):
    item = models.ForeignKey(SolicitacaoItem, on_delete=models.CASCADE, related_name='alocacoes')
    regional_origem = models.ForeignKey('Base', on_delete=models.CASCADE)
    quantidade = models.PositiveIntegerField()
    criado_em = models.DateTimeField(auto_now_add=True)
    equipamentos = models.ManyToManyField('Equipamento', through='AlocacaoEquipamento', blank=True)
    produto = models.ForeignKey('Produto', on_delete=models.CASCADE)

class AlocacaoEquipamento(models.Model):
    alocacao = models.ForeignKey(AlocacaoSolicitacaoItem, on_delete=models.CASCADE, related_name='itens_fisicos')
    equipamento = models.ForeignKey('Equipamento', on_delete=models.CASCADE)
    selecionado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('alocacao', 'equipamento')

class Transferencia(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', _('Pendente')
        EM_TRANSITO = 'EM_TRANSITO', _('Em trânsito')
        CONCLUIDA = 'CONCLUIDA', _('Concluída')
        CANCELADA = 'CANCELADA', _('Cancelada')

    class Origem(models.TextChoices):
        COMUM = 'COMUM', _('Transferência comum')
        SOLICITACAO = 'SOLICITACAO', _('Solicitação')
        AUDITORIA_DIVERGENCIA = 'AUDITORIA_DIVERGENCIA', _('Auditoria e divergência')
        DEVOLUCAO_EMPRESTIMO = 'DEVOLUCAO_EMPRESTIMO', _('Devolução de empréstimo')

    STATUS = Status.choices

#    equipamento = models.ForeignKey(Equipamento, null=True, blank=True, on_delete=models.SET_NULL)
    alocacao = models.ForeignKey(AlocacaoSolicitacaoItem,on_delete=models.SET_NULL, null=True, blank=True)
    solicitado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    regional_origem = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='origem')
    regional_destino = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='destino')
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.PENDENTE)
    origem_fluxo = models.CharField(
        max_length=30,
        choices=Origem.choices,
        default=Origem.COMUM,
        db_index=True,
    )
    aprovacao_admin_dispensada = models.BooleanField(default=False)
    motivo_dispensa_aprovacao = models.TextField(blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_envio = models.DateTimeField(null=True, blank=True)
    data_recebimento = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    protocolo = models.CharField(max_length=50, unique=True)
    codigo_rastreio = models.CharField(max_length=100, blank=True)

    @property
    def url_rastreio(self):
        return _url_rastreamento_correios(self.codigo_rastreio)

    def dias(self):
        from django.utils import timezone
        return (timezone.now() - self.created_at).days

    def enviar(self, codigo_rastreio=''):
        if self.status != self.Status.PENDENTE:
            raise ValueError("Só pode enviar se estiver pendente")

        self.status = self.Status.EM_TRANSITO
        self.data_envio = timezone.now()
        self.codigo_rastreio = (codigo_rastreio or '').strip()
        self.save(update_fields=['status', 'data_envio', 'codigo_rastreio', 'updated_at'])

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
        if self.status != self.Status.EM_TRANSITO:
            raise ValueError("Só pode receber se estiver enviado")

        self.status = self.Status.CONCLUIDA
        self.data_recebimento = timezone.now()
        self.save()

        itens = list(self.itens.select_related('equipamento'))
        equipamentos = []
        for item in itens:
            if item.equipamento_id:
                item.equipamento.regional = self.regional_destino
                item.equipamento.status = 'ATIVO'
                equipamentos.append(item.equipamento)
        if equipamentos:
            Equipamento.objects.bulk_update(equipamentos, ['regional', 'status'])
        self.itens.update(status='RECEBIDO')

    def cancelar(self):
        if self.status == self.Status.CONCLUIDA:
            raise ValueError(_("Transferência concluída não pode ser cancelada."))
        if self.status != self.Status.PENDENTE:
            raise ValueError(_("Somente transferências pendentes podem ser canceladas."))
        self.status = self.Status.CANCELADA
        self.save(update_fields=['status'])

class TransferenciaItem(models.Model):

    transferencia = models.ForeignKey(Transferencia, on_delete=models.CASCADE, related_name='itens')
    equipamento = models.ForeignKey(Equipamento, on_delete=models.CASCADE, null=True, blank=True)
    status = models.CharField(max_length=20, default='SELECIONADO')


class DeclaracaoCorreios(models.Model):
    class TipoOperacao(models.TextChoices):
        TRANSFERENCIA = 'TRANSFERENCIA', _('Transferência')
        EMPRESTIMO = 'EMPRESTIMO', _('Empréstimo')

    class Status(models.TextChoices):
        RASCUNHO = 'RASCUNHO', _('Rascunho')
        EMITIDA = 'EMITIDA', _('Emitida')
        SUBSTITUIDA = 'SUBSTITUIDA', _('Substituída')
        CANCELADA = 'CANCELADA', _('Cancelada')

    tipo_operacao = models.CharField(max_length=20, choices=TipoOperacao.choices, db_index=True)
    transferencia = models.ForeignKey(
        Transferencia,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='declaracoes_correios',
    )
    emprestimo = models.ForeignKey(
        Emprestimo,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='declaracoes_correios',
    )
    versao = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO)
    remetente = models.JSONField(default=dict)
    destinatario = models.JSONField(default=dict)
    resumo_operacao = models.JSONField(default=dict)
    quantidade_volumes = models.PositiveIntegerField(default=1)
    valor_total_declarado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    peso_total_kg = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    observacoes = models.TextField(blank=True)
    arquivo = models.FileField(upload_to='declaracoes_correios/%Y/%m/', blank=True)
    hash_arquivo = models.CharField(max_length=64, blank=True)
    gerada_por = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='declaracoes_correios_geradas',
    )
    gerada_em = models.DateTimeField(auto_now_add=True)
    substituida_por = models.OneToOneField(
        'self',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='substitui',
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(transferencia__isnull=False, emprestimo__isnull=True)
                    | Q(transferencia__isnull=True, emprestimo__isnull=False)
                ),
                name='ck_declaracao_exatamente_uma_operacao',
            ),
            models.UniqueConstraint(
                fields=['transferencia', 'versao'],
                condition=Q(transferencia__isnull=False),
                name='uq_declaracao_transferencia_versao',
            ),
            models.UniqueConstraint(
                fields=['emprestimo', 'versao'],
                condition=Q(emprestimo__isnull=False),
                name='uq_declaracao_emprestimo_versao',
            ),
        ]

    def clean(self):
        super().clean()
        if bool(self.transferencia_id) == bool(self.emprestimo_id):
            raise ValidationError(_('Informe exatamente uma operação.'))
        tipo_esperado = (
            self.TipoOperacao.TRANSFERENCIA
            if self.transferencia_id
            else self.TipoOperacao.EMPRESTIMO
        )
        if self.tipo_operacao != tipo_esperado:
            raise ValidationError({'tipo_operacao': _('Tipo incompatível com a operação informada.')})


class DeclaracaoCorreiosItem(models.Model):
    declaracao = models.ForeignKey(
        DeclaracaoCorreios,
        on_delete=models.CASCADE,
        related_name='itens',
    )
    equipamento = models.ForeignKey(Equipamento, null=True, blank=True, on_delete=models.PROTECT)
    descricao = models.CharField(max_length=255)
    quantidade = models.PositiveIntegerField(default=1)
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    patrimonio = models.CharField(max_length=100, blank=True)
    numero_serie = models.CharField(max_length=150, blank=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordem', 'id']

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

    transferencia = models.ForeignKey(Transferencia, null=True, blank=True, on_delete=models.CASCADE)
    solicitacao = models.ForeignKey(Solicitacao, null=True, blank=True, on_delete=models.SET_NULL)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
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
    regional_origem = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='pedidos_origem')
    regional_destino = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='pedidos_destino')
    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, default='ABERTO')

class PedidoItem(models.Model):

    pedido = models.ForeignKey(PedidoTransferencia, related_name='itens', on_delete=models.CASCADE)
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.IntegerField()

class TransferRequest(models.Model):

    STATUS = [
        ('ABERTO', 'Aberto'),
        ('ENVIADO', 'Enviado para origem'),
        ('EXECUTANDO', 'Em execução'),
        ('FINALIZADO', 'Finalizado'),
    ]

    solicitacao = models.ForeignKey(Solicitacao, on_delete=models.CASCADE)
    categoria = models.CharField(max_length=50)
    quantidade = models.PositiveIntegerField()
    regional_origem = models.ForeignKey(Base, related_name='requests_origem', on_delete=models.CASCADE)
    regional_destino = models.ForeignKey(Base, related_name='requests_destino', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='ABERTO')
    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

class DivergenciaTransferencia(models.Model):

    transferencia = models.ForeignKey(Transferencia, on_delete=models.CASCADE)
    item = models.ForeignKey(TransferenciaItem, on_delete=models.CASCADE)
    equipamento_enviado = models.ForeignKey(Equipamento, on_delete=models.PROTECT, related_name='divergencias_enviadas')
    serie_recebida = models.CharField(max_length=100, blank=True)
    patrimonio_recebido = models.CharField(max_length=100, blank=True)
    observacao = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)
    resolvida = models.BooleanField(default=False)

class PendenciaTransferencia(models.Model):

    STATUS = [
        ('ABERTA', 'Aberta'),
        ('EM_ANALISE', 'Em análise'),
        ('RESOLVIDA', 'Resolvida'),
    ]

    TIPO = [
        ('DIVERGENCIA', 'Divergência'),
        ('NAO_RECEBIDO', 'Não recebido'),
    ]

    transferencia = models.ForeignKey(Transferencia, on_delete=models.CASCADE, related_name='pendencias')
    item = models.ForeignKey(TransferenciaItem, on_delete=models.CASCADE, related_name='pendencias')
    tipo = models.CharField(max_length=30, choices=TIPO)
    patrimonio_esperado = models.CharField(max_length=100, blank=True)
    serie_esperada = models.CharField(max_length=150, blank=True)
    patrimonio_recebido = models.CharField(max_length=100, blank=True)
    serie_recebida = models.CharField(max_length=150, blank=True)
    descricao = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='ABERTA')
    criado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)
    equipamento = models.ForeignKey(Equipamento, on_delete=models.PROTECT)
    motivo = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return (
            f'{self.transferencia.protocolo} - '
            f'{self.tipo}'
        )

# ---------------- SICK ----------------
class StatusEquipamento(models.TextChoices):
    ATIVO = 'ATIVO', _('Ativo')
    SICK = 'SICK', _('SICK')
    MANUTENCAO = 'MANUTENCAO', _('Manutenção')
    SUCATA= 'SUCATA', _('Sucata')
    INATIVO = 'INATIVO', _('Inativo')

class Sick(models.Model):
    class TipoDestino(models.TextChoices):
        MATRIZ = 'MATRIZ', _('Matriz')
        TERCEIRIZADA = 'TERCEIRIZADA', _('Manutenção terceirizada')

    class Etapa(models.TextChoices):
        IDENTIFICADO = 'IDENTIFICADO', _('Identificado na base')
        EM_TRANSITO = 'EM_TRANSITO', _('Em trânsito para manutenção')
        RECEBIDO = 'RECEBIDO', _('Recebido pela manutenção')
        EM_AVALIACAO = 'EM_AVALIACAO', _('Em avaliação técnica')
        EM_MANUTENCAO = 'EM_MANUTENCAO', _('Em manutenção')
        AGUARDANDO_RETORNO = 'AGUARDANDO_RETORNO', _('Aguardando retorno para a base')
        FINALIZADO = 'FINALIZADO', _('Finalizado')

    equipamento = models.ForeignKey(Equipamento, on_delete=models.CASCADE, related_name='sicks')
    base_origem = models.ForeignKey(
        Base,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='sicks_originados',
    )
    tipo_destino = models.CharField(
        max_length=20,
        choices=TipoDestino.choices,
        blank=True,
        db_index=True,
    )
    categoria = models.CharField(max_length=100)
    motivo = models.TextField(blank=True, null=True)
    previsao_retorno = models.DateField(null=True, blank=True)
    data_ocorrencia = models.DateTimeField(auto_now_add=True, db_index=True)
    data_resolucao = models.DateTimeField(null=True, blank=True)
    resolvido_por = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    ativo = models.BooleanField(default=True, db_index=True)
    descricao = models.TextField(null=True, blank=True)
    status_final = models.CharField(max_length=40, choices=StatusEquipamento.choices, null=True, blank=True)
    observacao_resolucao = models.TextField(null=True, blank=True)
    etapa = models.CharField(
        max_length=30,
        choices=Etapa.choices,
        default=Etapa.IDENTIFICADO,
        db_index=True,
    )
    enviado_manutencao_em = models.DateTimeField(null=True, blank=True)
    enviado_manutencao_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='sicks_enviados_manutencao',
    )
    recebido_manutencao_em = models.DateTimeField(null=True, blank=True)
    recebido_manutencao_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='sicks_recebidos_manutencao',
    )
    avaliacao_iniciada_em = models.DateTimeField(null=True, blank=True)
    avaliacao_iniciada_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='sicks_avaliados',
    )
    manutencao_iniciada_em = models.DateTimeField(null=True, blank=True)
    manutencao_iniciada_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='sicks_manutencao_iniciada',
    )
    manutencao_concluida_em = models.DateTimeField(null=True, blank=True)
    manutencao_concluida_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='sicks_manutencao_concluida',
    )
    retorno_confirmado_em = models.DateTimeField(null=True, blank=True)
    retorno_confirmado_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='sicks_retorno_confirmado',
    )
    destino_manutencao = models.CharField(max_length=255, blank=True)
    protocolo_envio = models.CharField(max_length=100, blank=True)
    codigo_rastreio_envio = models.CharField(max_length=100, blank=True)
    codigo_rastreio_retorno = models.CharField(max_length=100, blank=True)
    transportadora_ou_portador = models.CharField(max_length=255, blank=True)
    causa_identificada = models.TextField(blank=True)
    diagnostico = models.TextField(blank=True)
    solucao_aplicada = models.TextField(blank=True)
    resultado_manutencao = models.TextField(blank=True)
    apto_retorno = models.BooleanField(null=True, blank=True)
    observacao_tecnica = models.TextField(blank=True)

    @property
    def url_rastreio_envio(self):
        return _url_rastreamento_correios(self.codigo_rastreio_envio)

    @property
    def url_rastreio_retorno(self):
        return _url_rastreamento_correios(self.codigo_rastreio_retorno)

    class Meta:
        permissions = [
            ('enviar_equipamento_manutencao', 'Pode enviar equipamento para manutenção'),
            ('receber_equipamento_manutencao', 'Pode confirmar recebimento na manutenção'),
            ('avaliar_equipamento_sick', 'Pode avaliar equipamento SICK'),
            ('iniciar_manutencao_equipamento', 'Pode iniciar manutenção'),
            ('concluir_manutencao_equipamento', 'Pode concluir manutenção'),
            ('confirmar_retorno_equipamento', 'Pode confirmar retorno do equipamento'),
            ('corrigir_fluxo_sick', 'Pode corrigir etapas do fluxo SICK'),
        ]

# ---------------- HISTORICO ----------------
class Historico(models.Model):
    TIPO_ACOES = [
        ('CRIACAO', _('Criação')),
        ('TRANSFERENCIA', _('Transferência')),
        ('STATUS', _('SICK')),
        ('EDICAO', _('Edição')),
        ('SICK', _('Marcado como SICK')),
        ('SICK_ATUALIZADO', _('SICK atualizado')),
        ('SICK_ENVIO_MANUTENCAO', _('Enviado para manutenção')),
        ('SICK_RECEBIMENTO_MANUTENCAO', _('Recebido pela manutenção')),
        ('SICK_AVALIACAO', _('Avaliação técnica iniciada')),
        ('MANUTENCAO_INICIADA', _('Manutenção iniciada')),
        ('MANUTENCAO_ATUALIZADA', _('Manutenção atualizada')),
        ('MANUTENCAO_CONCLUIDA', _('Manutenção concluída')),
        ('SICK_AGUARDANDO_RETORNO', _('Aguardando retorno')),
        ('SICK_RETORNO_CONFIRMADO', _('Retorno confirmado')),
        ('RESOLUCAO_SICK', _('SICK finalizado')),
        ('SICK_REABERTO', _('SICK reaberto')),
        ('AUDITORIA_LOCALIZADO', _('Localizado em auditoria')),
        ('AUDITORIA_DIVERGENCIA', _('Divergência de auditoria')),
        ('AUDITORIA_BASE_ATUALIZADA', _('Base atualizada por auditoria')),
        ('AUDITORIA_TRANSFERENCIA', _('Transferência criada por auditoria')),
        ('AUDITORIA_REGULARIZADA', _('Regularizado por auditoria')),
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

# ---------------- MENSAGENS ----------------
class Comunicado(models.Model):

    TIPOS = [
        ('INFO', 'Informativo'),
        ('URGENTE', 'Urgente'),
        ('MANUTENCAO', 'Manutenção'),
        ('OPERACIONAL', 'Operacional'),
    ]

    titulo = models.CharField(max_length=150)
    mensagem = models.TextField()
    tipo = models.CharField(max_length=20, choices=TIPOS, default='INFO')
    criado_por = models.ForeignKey(User, on_delete=models.CASCADE)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True)
    enviar_para_todos = models.BooleanField(default=False)
    usuarios = models.ManyToManyField(User, blank=True, related_name='comunicados')
    criado_em = models.DateTimeField(auto_now_add=True)
    ativo = models.BooleanField(default=True)
    expira_em = models.DateTimeField(null=True, blank=True)
    permitir_limpar = models.BooleanField(default=True)
    dados = models.JSONField(blank=True, null=True)
    url = models.CharField(max_length=500, blank=True)

    def expirado(self):
        from django.utils import timezone

        return (
            self.expira_em and
            timezone.now() >= self.expira_em
        )

    def save(self, *args, **kwargs):
        if not self.expira_em:
            from django.utils import timezone

            self.expira_em = timezone.now() + timedelta(days=30)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.titulo


class ComunicadoEntrega(models.Model):
    class Canal(models.TextChoices):
        SISTEMA = 'SISTEMA', _('Sistema')
        EMAIL = 'EMAIL', _('E-mail')
        WHATSAPP = 'WHATSAPP', _('WhatsApp')

    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', _('Pendente')
        PROCESSANDO = 'PROCESSANDO', _('Processando')
        ENVIADA = 'ENVIADA', _('Enviada')
        ENTREGUE = 'ENTREGUE', _('Entregue')
        LIDA = 'LIDA', _('Lida')
        FALHA = 'FALHA', _('Falha')
        CANCELADA = 'CANCELADA', _('Cancelada')
        IGNORADA = 'IGNORADA', _('Ignorada')

    comunicado = models.ForeignKey(Comunicado, on_delete=models.CASCADE, related_name='entregas')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='entregas_comunicados')
    canal = models.CharField(max_length=20, choices=Canal.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE, db_index=True)
    destino = models.CharField(max_length=180)
    provedor = models.CharField(max_length=50, blank=True)
    template_codigo = models.CharField(max_length=100, blank=True)
    parametros = models.JSONField(default=dict, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    provider_resposta = models.JSONField(default=dict, blank=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True)
    tentativas = models.PositiveIntegerField(default=0)
    proxima_tentativa_em = models.DateTimeField(null=True, blank=True, db_index=True)
    ultimo_erro = models.TextField(blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    processada_em = models.DateTimeField(null=True, blank=True)
    enviada_em = models.DateTimeField(null=True, blank=True)
    entregue_em = models.DateTimeField(null=True, blank=True)
    lida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['comunicado', 'usuario', 'canal'],
                name='uq_comunicado_usuario_canal',
            )
        ]
        indexes = [models.Index(fields=['canal', 'status', 'proxima_tentativa_em'])]

class ComunicadoArquivo(models.Model):

    comunicado = models.ForeignKey(Comunicado, on_delete=models.CASCADE, related_name='arquivos')
    arquivo = models.FileField(upload_to='comunicados/')
    enviado_em = models.DateTimeField(auto_now_add=True)

class ComunicadoLeitura(models.Model):

    comunicado = models.ForeignKey(Comunicado, on_delete=models.CASCADE, related_name='leituras')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    lido_em = models.DateTimeField(auto_now_add=True)

class ComunicadoOculto(models.Model):

    comunicado = models.ForeignKey(Comunicado, on_delete=models.CASCADE)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    ocultado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('comunicado', 'usuario')

class Mensagem(models.Model):

    titulo = models.CharField(max_length=200)
    conteudo = models.TextField()
    enviado_por = models.ForeignKey(User, on_delete=models.CASCADE)
    enviado_em = models.DateTimeField(auto_now_add=True)

class MensagemDestino(models.Model):

    mensagem = models.ForeignKey(Mensagem, related_name='destinos', on_delete=models.CASCADE)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    lido = models.BooleanField(default=False)
    data_leitura = models.DateTimeField(null=True, blank=True)

class MensagemArquivo(models.Model):

    mensagem = models.ForeignKey(Mensagem, related_name='arquivos', on_delete=models.CASCADE)
    arquivo = models.FileField(upload_to='mensagens/')
    nome_original = models.CharField(max_length=255)

@receiver([post_save, post_delete], sender=Equipamento)
def limpar_cache_estoque(sender, instance, **kwargs):
    cache_keys = [
        'views.decorators.cache.cache_page.*',
        f'estoque_regional_{instance.regional_id}',
        'estoque_kpis_gerais',
    ]
    for key in cache_keys:
        cache.delete(key)
