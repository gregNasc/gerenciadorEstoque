from django.utils import timezone
from estoque.models import Transferencia, Historico


def gerar_transferencias_da_solicitacao(solicitacao, origem, user):

    equipamentos = Equipamento.objects.filter(
        produto=solicitacao.produto,
        regional=origem,
        status='ATIVO'
    )[:solicitacao.quantidade]

    for e in equipamentos:
        iniciar_transferencia(
            equipamento=e,
            destino=solicitacao.regional_solicitante,
            user=user,
            solicitacao=solicitacao
        )

        transferencias.append(t)

    return transferencias

def iniciar_transferencia(equipamento, destino, user, solicitacao=None):
    transferencia = Transferencia.objects.create(
        solicitacao=solicitacao,
        alocacao=None,
        regional_origem=equipamento.regional,
        regional_destino=destino,
        solicitado_por=user,
        status='PENDENTE'
    )
    equipamento.status = 'TRANSFERENCIA'
    equipamento.save(update_fields=['status'])

    return transferencia

def finalizar_transferencia(transferencia, user):

    transferencia.status = 'RECEBIDO'
    transferencia.data_recebimento = timezone.now()
    transferencia.save(update_fields=['status', 'data_recebimento'])

    # movimenta todos os equipamentos dos itens
    for item in transferencia.itens.all():
        for eq in item.equipamentos.all():

            eq.regional = transferencia.regional_destino
            eq.status = 'ATIVO'
            eq.save(update_fields=['regional', 'status'])

            Historico.objects.create(
                equipamento=eq,
                tipo_acao='TRANSFERENCIA',
                usuario=user,
                detalhes={
                    'origem': transferencia.regional_origem.nome,
                    'destino': transferencia.regional_destino.nome,
                    'transferencia_id': transferencia.id
                }
            )

def cancelar_transferencia(transferencia, user):

    if transferencia.status != Transferencia.Status.PENDENTE:
        return False

    transferencia.status = Transferencia.Status.CANCELADO
    transferencia.save(update_fields=['status'])

    equipamento = transferencia.equipamento
    equipamento.status = 'ATIVO'
    equipamento.save(update_fields=['status'])

    Historico.objects.create(
        equipamento=equipamento,
        tipo_acao='TRANSFERENCIA_CANCELADA',
        usuario=user,
        detalhes={
            'origem': transferencia.regional_origem.nome,
            'destino': transferencia.regional_destino.nome,
        }
    )

    return True