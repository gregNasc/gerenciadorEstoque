from django.urls import reverse
from .models import Comunicado
from .services.comunicados import (
    gerar_comunicado_da_notificacao,
    adicionar_link
)


def gerar_comunicado_da_notificacao(notificacao):

    # TRANSFERÊNCIA CRIADA
    if notificacao.tipo == "TRANSFERENCIA" and notificacao.evento == "EM_TRANSFERENCIA":
        transferencia = notificacao.transferencia

        return Comunicado.objects.create(
            titulo=f"Transferência #{transferencia.id}",
            mensagem="Há uma transferência aguardando recebimento.",
            tipo="OPERACIONAL",
            criado_por=notificacao.usuario,
            enviar_para_todos=False,
        )

    # SOLICITAÇÃO APROVADA
    if notificacao.tipo == "SOLICITACAO" and notificacao.evento == "APROVADA":
        solicitacao = notificacao.solicitacao

        return Comunicado.objects.create(
            titulo=f"Solicitação #{solicitacao.id} aprovada",
            mensagem="Uma solicitação foi aprovada e precisa de atendimento.",
            tipo="OPERACIONAL",
            criado_por=notificacao.usuario,
            enviar_para_todos=False,
        )

    return None

def adicionar_link(comunicado, notificacao):
    if notificacao.transferencia:
        comunicado.link = f"/transferencias/receber/{notificacao.transferencia.id}/"

    elif notificacao.solicitacao:
        comunicado.link = f"/solicitacoes/{notificacao.solicitacao.id}/"

    comunicado.save()

def criar_notificacao():
    notificacao = Notificacao.objects.create(...)

    comunicado = gerar_comunicado_da_notificacao(notificacao)

    if comunicado:
        adicionar_link(comunicado, notificacao)

    return notificacao