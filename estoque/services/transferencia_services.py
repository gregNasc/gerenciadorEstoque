# estoque/services/transferencia_services.py

from django.db import transaction
from django.utils import timezone

from estoque.models import (
    Equipamento,
    Transferencia,
    TransferenciaItem,
    Historico,
    Notificacao,
)

STATUS_PENDENTE = 'PENDENTE'
STATUS_EM_TRANSITO = 'EM_TRANSITO'
STATUS_CONCLUIDA = 'CONCLUIDA'
STATUS_CANCELADA = 'CANCELADA'

def validar_transferencia(equipamento):

    if equipamento.status == 'SICK':
        return False, 'Equipamento em SICK'

    if equipamento.status != 'ATIVO':
        return False, 'Equipamento indisponível'

    existe = TransferenciaItem.objects.filter(
        equipamento=equipamento,
        transferencia__status__in=[
            STATUS_PENDENTE,
            STATUS_EM_TRANSITO
        ]
    ).exists()

    if existe:
        return False, 'Equipamento já possui transferência pendente'

    return True, None

@transaction.atomic
def criar_transferencia(*, equipamentos, regional_destino, solicitado_por, alocacao=None):

    if not equipamentos:
        raise ValueError('Nenhum equipamento informado.')

    equipamentos = list(equipamentos)

    regional_origem = equipamentos[0].regional

    for equipamento in equipamentos:

        if equipamento.regional_id != regional_origem.id:
            raise ValueError(
                'Todos os equipamentos devem possuir a mesma regional de origem.'
            )

    for equipamento in equipamentos:

        pode, motivo = validar_transferencia(equipamento)

        if not pode:
            raise ValueError(
                f'{equipamento.numero_serie}: {motivo}'
            )

    transferencia = Transferencia.objects.create(
        alocacao=alocacao,
        solicitado_por=solicitado_por,
        regional_origem=regional_origem,
        regional_destino=regional_destino,
        status=STATUS_PENDENTE
    )

    itens = []

    for equipamento in equipamentos:

        item = TransferenciaItem(
            transferencia=transferencia,
            equipamento=equipamento,
            status='SELECIONADO'
        )

        itens.append(item)

    TransferenciaItem.objects.bulk_create(itens)

    for equipamento in equipamentos:

        equipamento.status = 'EM_TRANSITO'

    Equipamento.objects.bulk_update(
        equipamentos,
        ['status']
    )

    historicos = []

    for equipamento in equipamentos:

        historicos.append(
            Historico(
                equipamento=equipamento,
                tipo_acao='TRANSFERENCIA_CRIADA',
                usuario=solicitado_por,
                detalhes={
                    'transferencia_id': transferencia.id,
                    'origem': regional_origem.nome,
                    'destino': regional_destino.nome,
                }
            )
        )

    Historico.objects.bulk_create(historicos)

    usuarios_destino = (
        regional_destino.perfis
        .select_related('user')
        .all()
    )

    notificacoes = []

    for perfil in usuarios_destino:

        if not perfil.user:
            continue

        notificacoes.append(
            Notificacao(
                usuario=perfil.user,
                transferencia=transferencia,
                tipo='TRANSFERENCIA',
                evento='CRIADA',
                mensagem=(
                    f'Nova transferência recebida '
                    f'de {regional_origem.nome}'
                ),
                link=f'/transferencias/{transferencia.id}/'
            )
        )

    Notificacao.objects.bulk_create(
        notificacoes,
        ignore_conflicts=True
    )

    return transferencia

@transaction.atomic
def enviar_transferencia(transferencia, user):

    if transferencia.status != STATUS_PENDENTE:
        raise ValueError(
            'Somente transferências pendentes podem ser enviadas.'
        )

    transferencia.status = STATUS_EM_TRANSITO
    transferencia.data_envio = timezone.now()

    transferencia.save(
        update_fields=[
            'status',
            'data_envio'
        ]
    )

    # -----------------------------------------------------
    # histórico
    # -----------------------------------------------------

    historicos = []

    for item in transferencia.itens.select_related('equipamento'):

        historicos.append(
            Historico(
                equipamento=item.equipamento,
                tipo_acao='TRANSFERENCIA_ENVIADA',
                usuario=user,
                detalhes={
                    'transferencia_id': transferencia.id,
                    'origem': transferencia.regional_origem.nome,
                    'destino': transferencia.regional_destino.nome,
                }
            )
        )

    Historico.objects.bulk_create(historicos)

    # -----------------------------------------------------
    # notificações
    # -----------------------------------------------------

    usuarios_destino = (
        transferencia.regional_destino.perfis
        .select_related('user')
        .all()
    )

    notificacoes = []

    for perfil in usuarios_destino:

        if not perfil.user:
            continue

        notificacoes.append(
            Notificacao(
                usuario=perfil.user,
                transferencia=transferencia,
                tipo='TRANSFERENCIA',
                evento='EM_TRANSFERENCIA',
                mensagem=(
                    f'Transferência em trânsito '
                    f'de {transferencia.regional_origem.nome}'
                ),
                link=f'/transferencias/{transferencia.id}/'
            )
        )

    Notificacao.objects.bulk_create(
        notificacoes,
        ignore_conflicts=True
    )

    return transferencia

@transaction.atomic
def receber_transferencia(transferencia, user):

    if transferencia.status != STATUS_EM_TRANSITO:
        raise ValueError(
            'Somente transferências em trânsito podem ser recebidas.'
        )

    transferencia.status = STATUS_CONCLUIDA
    transferencia.data_recebimento = timezone.now()

    transferencia.save(
        update_fields=[
            'status',
            'data_recebimento'
        ]
    )

    itens = list(
        transferencia.itens.select_related('equipamento')
    )

    equipamentos = []

    historicos = []

    for item in itens:

        equipamento = item.equipamento

        equipamento.regional = transferencia.regional_destino
        equipamento.status = 'ATIVO'

        equipamentos.append(equipamento)

        historicos.append(
            Historico(
                equipamento=equipamento,
                tipo_acao='TRANSFERENCIA_RECEBIDA',
                usuario=user,
                detalhes={
                    'transferencia_id': transferencia.id,
                    'origem': transferencia.regional_origem.nome,
                    'destino': transferencia.regional_destino.nome,
                }
            )
        )

    Equipamento.objects.bulk_update(
        equipamentos,
        ['regional', 'status']
    )

    Historico.objects.bulk_create(historicos)

    return transferencia

@transaction.atomic
def cancelar_transferencia(transferencia, user):

    if transferencia.status != STATUS_PENDENTE:
        raise ValueError(
            'Somente transferências pendentes podem ser canceladas.'
        )

    transferencia.status = STATUS_CANCELADA

    transferencia.save(
        update_fields=['status']
    )

    itens = list(
        transferencia.itens.select_related('equipamento')
    )

    equipamentos = []

    historicos = []

    for item in itens:

        equipamento = item.equipamento

        equipamento.status = 'ATIVO'

        equipamentos.append(equipamento)

        historicos.append(
            Historico(
                equipamento=equipamento,
                tipo_acao='TRANSFERENCIA_CANCELADA',
                usuario=user,
                detalhes={
                    'transferencia_id': transferencia.id,
                    'origem': transferencia.regional_origem.nome,
                    'destino': transferencia.regional_destino.nome,
                }
            )
        )

    Equipamento.objects.bulk_update(
        equipamentos,
        ['status']
    )

    Historico.objects.bulk_create(historicos)

    return transferencia

@transaction.atomic
def gerar_transferencias_da_solicitacao(solicitacao, origem, user):

    transferencias = []

    for item in solicitacao.itens.all():

        equipamentos = list(
            Equipamento.objects.filter(
                produto__categoria=item.categoria,
                regional=origem,
                status='ATIVO'
            )[:item.quantidade]
        )

        if not equipamentos:
            continue

        transferencia = criar_transferencia(
            equipamentos=equipamentos,
            regional_destino=solicitacao.regional_solicitante,
            solicitado_por=user
        )

        enviar_transferencia(
            transferencia,
            user
        )

        transferencias.append(transferencia)

        item.atendido += len(equipamentos)

        item.save(update_fields=['atendido'])

    solicitacao.status = 'EM_TRANSFERENCIA'

    solicitacao.save(update_fields=['status'])

    return transferencias