from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class SequenciaOrdemServico(models.Model):
    empresa = models.ForeignKey('estoque.Empresa', on_delete=models.CASCADE)
    ano = models.PositiveSmallIntegerField()
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['empresa', 'ano'], name='os_sequencia_empresa_ano_unica'),
        ]


class OrdemServico(models.Model):
    class Tipo(models.TextChoices):
        TRANSFERENCIA = 'TRANSFERENCIA', 'Transferência'
        SICK = 'SICK', 'SICK'
        EMPRESTIMO = 'EMPRESTIMO', 'Empréstimo'
        INSUMO = 'INSUMO', 'Movimentação de insumo'
        CONSUMO = 'CONSUMO', 'Consumo'
        MANUTENCAO = 'MANUTENCAO', 'Manutenção'
        OUTRO = 'OUTRO', 'Outro'

    class Prioridade(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        URGENTE = 'URGENTE', 'Urgente'
        EMERGENCIAL = 'EMERGENCIAL', 'Emergencial'

    class Status(models.TextChoices):
        RASCUNHO = 'RASCUNHO', 'Rascunho'
        AGUARDANDO_AUTORIZACAO = 'AGUARDANDO_AUTORIZACAO', 'Aguardando autorização'
        AUTORIZADA = 'AUTORIZADA', 'Autorizada'
        EM_EXECUCAO = 'EM_EXECUCAO', 'Em execução'
        AGUARDANDO_CONFIRMACAO = 'AGUARDANDO_CONFIRMACAO', 'Aguardando confirmação'
        CONCLUIDA = 'CONCLUIDA', 'Concluída'
        CANCELADA = 'CANCELADA', 'Cancelada'

    numero = models.CharField(max_length=20, db_index=True)
    ano = models.PositiveSmallIntegerField(db_index=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, db_index=True)
    prioridade = models.CharField(max_length=15, choices=Prioridade.choices, default=Prioridade.NORMAL)
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.AGUARDANDO_AUTORIZACAO,
        db_index=True,
    )
    empresa = models.ForeignKey('estoque.Empresa', on_delete=models.PROTECT, related_name='ordens_servico')
    base_responsavel = models.ForeignKey(
        'estoque.Base', null=True, blank=True, on_delete=models.PROTECT, related_name='ordens_servico_responsavel'
    )
    base_origem = models.ForeignKey(
        'estoque.Base', null=True, blank=True, on_delete=models.PROTECT, related_name='ordens_servico_origem'
    )
    base_destino = models.ForeignKey(
        'estoque.Base', null=True, blank=True, on_delete=models.PROTECT, related_name='ordens_servico_destino'
    )
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ordens_servico_solicitadas'
    )
    responsavel_operacional = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='ordens_servico_responsavel_operacional',
    )
    autorizador = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='ordens_servico_autorizadas',
    )
    recebedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='ordens_servico_recebidas',
    )
    motivo = models.TextField()
    descricao = models.TextField(blank=True)
    justificativa_urgencia = models.TextField(blank=True)
    prazo_em = models.DateTimeField(null=True, blank=True)
    aberto_em = models.DateTimeField(auto_now_add=True)
    autorizado_em = models.DateTimeField(null=True, blank=True)
    executado_em = models.DateTimeField(null=True, blank=True)
    confirmado_em = models.DateTimeField(null=True, blank=True)
    encerrado_em = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.TextField(blank=True)
    chamado_referencia = models.CharField(max_length=80, blank=True)
    transferencia = models.OneToOneField(
        'estoque.Transferencia', null=True, blank=True, on_delete=models.PROTECT, related_name='ordem_servico'
    )
    sick = models.OneToOneField(
        'estoque.Sick', null=True, blank=True, on_delete=models.PROTECT, related_name='ordem_servico'
    )
    emprestimo = models.OneToOneField(
        'estoque.Emprestimo', null=True, blank=True, on_delete=models.PROTECT, related_name='ordem_servico'
    )
    solicitacao_insumo = models.OneToOneField(
        'insumos.SolicitacaoInsumo', null=True, blank=True, on_delete=models.PROTECT,
        related_name='ordem_servico',
    )
    movimentacao_insumo = models.OneToOneField(
        'insumos.MovimentacaoInsumo', null=True, blank=True, on_delete=models.PROTECT,
        related_name='ordem_servico',
    )

    class Meta:
        ordering = ['-aberto_em', '-id']
        constraints = [
            models.UniqueConstraint(fields=['empresa', 'numero'], name='os_numero_empresa_unico'),
            models.CheckConstraint(
                condition=(
                    models.Q(prioridade='NORMAL')
                    | ~models.Q(justificativa_urgencia='')
                ),
                name='os_urgencia_exige_justificativa',
            ),
        ]
        permissions = [
            ('autorizar_ordem_servico', 'Pode autorizar ordem de serviço'),
            ('visualizar_todas_ordens_servico', 'Pode visualizar todas as ordens de serviço'),
        ]

    def clean(self):
        super().clean()
        for campo in ('base_responsavel', 'base_origem', 'base_destino'):
            base = getattr(self, campo, None)
            if base and base.empresa_id != self.empresa_id:
                raise ValidationError({campo: 'A base deve pertencer à empresa da O.S.'})
        if self.prioridade != self.Prioridade.NORMAL and not self.justificativa_urgencia.strip():
            raise ValidationError({'justificativa_urgencia': 'Informe a justificativa da urgência.'})

    def __str__(self):
        return self.numero


class OrdemServicoLinha(models.Model):
    class Natureza(models.TextChoices):
        EQUIPAMENTO = 'EQUIPAMENTO', 'Equipamento'
        INSUMO_TRANSFERIDO = 'INSUMO_TRANSFERIDO', 'Insumo transferido'
        INSUMO_CONSUMIDO = 'INSUMO_CONSUMIDO', 'Insumo consumido'
        PECA = 'PECA', 'Peça de manutenção'
        DEVOLUCAO = 'DEVOLUCAO', 'Item devolvido'
        PERDA_AVARIA = 'PERDA_AVARIA', 'Perda ou avaria'

    ordem = models.ForeignKey(OrdemServico, on_delete=models.CASCADE, related_name='linhas')
    natureza = models.CharField(max_length=25, choices=Natureza.choices)
    equipamento = models.ForeignKey('estoque.Equipamento', null=True, blank=True, on_delete=models.PROTECT)
    insumo = models.ForeignKey('insumos.Insumo', null=True, blank=True, on_delete=models.PROTECT)
    descricao = models.CharField(max_length=255)
    fabricante = models.CharField(max_length=100, blank=True)
    modelo = models.CharField(max_length=100, blank=True)
    codigo = models.CharField(max_length=100, blank=True)
    unidade = models.CharField(max_length=30, blank=True)
    quantidade = models.DecimalField(max_digits=14, decimal_places=2, default=1)
    lote = models.CharField(max_length=100, blank=True)
    validade = models.DateField(null=True, blank=True)
    patrimonio = models.CharField(max_length=100, blank=True)
    numero_serie = models.CharField(max_length=150, blank=True)
    origem = models.CharField(max_length=150, blank=True)
    destino = models.CharField(max_length=150, blank=True)
    condicao_saida = models.CharField(max_length=120, blank=True)
    condicao_retorno = models.CharField(max_length=120, blank=True)
    custo_unitario_historico = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    dados_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(condition=models.Q(quantidade__gt=0), name='os_linha_quantidade_positiva'),
        ]


class OrdemServicoAssinatura(models.Model):
    class Tipo(models.TextChoices):
        AUTORIZACAO = 'AUTORIZACAO', 'Autorização'
        EXECUCAO = 'EXECUCAO', 'Execução'
        RECEBIMENTO = 'RECEBIMENTO', 'Recebimento'
        ENCERRAMENTO = 'ENCERRAMENTO', 'Encerramento'

    ordem = models.ForeignKey(OrdemServico, on_delete=models.PROTECT, related_name='assinaturas')
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    assinado_em = models.DateTimeField(auto_now_add=True)
    hash_documento = models.CharField(max_length=64)
    versao_documento = models.PositiveIntegerField(default=1)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['ordem', 'tipo'], name='os_assinatura_tipo_unica'),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Assinaturas digitais são imutáveis.')
        return super().save(*args, **kwargs)


class OrdemServicoEvento(models.Model):
    ordem = models.ForeignKey(OrdemServico, on_delete=models.CASCADE, related_name='eventos')
    tipo = models.CharField(max_length=60, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    dados = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['criado_em', 'id']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Eventos de O.S. são imutáveis.')
        return super().save(*args, **kwargs)


class OrdemServicoAnexo(models.Model):
    ordem = models.ForeignKey(OrdemServico, on_delete=models.PROTECT, related_name='anexos')
    arquivo = models.FileField(upload_to='ordens_servico/%Y/%m/')
    nome_original = models.CharField(max_length=255)
    hash_arquivo = models.CharField(max_length=64)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    enviado_em = models.DateTimeField(auto_now_add=True)
