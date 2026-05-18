from django.utils import timezone

def criar_transferencia_da_alocacao(alocacao):
    transferencia = Transferencia.objects.create(
        alocacao=alocacao,
        solicitado_por=alocacao.item.solicitacao.criado_por,
        regional_origem=alocacao.regional_origem,
        regional_destino=alocacao.item.solicitacao.regional_solicitante,
        status='PENDENTE'
    )

    equipamentos = alocacao.equipamentos.all()

    for eq in equipamentos:
        TransferenciaItem.objects.create(
            transferencia=transferencia,
            equipamento=eq,
            status='SELECIONADO'
        )

        eq.status = 'RESERVADO_TRANSFERENCIA'
        eq.save()

    return transferencia