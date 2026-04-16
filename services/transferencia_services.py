from django.utils import timezone
from .models import Transferencia, Equipamento

def gerar_transferencias_da_solicitacao(solicitacao, origem, user):
    equipamentos = Equipamento.objects.filter(
        produto=solicitacao.produto,
        regional=origem,
        status='ATIVO'
    )[:solicitacao.quantidade]

    transferencias = []

    for e in equipamentos:
        e.status = 'TRANSFERENCIA'
        e.save(update_fields=['status'])

        t = Transferencia.objects.create(
            solicitacao=solicitacao,
            equipamento=e,
            regional_origem=origem,
            regional_destino=solicitacao.regional_solicitante,
            solicitado_por=user,
            status='PENDENTE'
        )

        transferencias.append(t)

    return transferencias