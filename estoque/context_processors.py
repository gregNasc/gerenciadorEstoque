from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from estoque.permissions import pode_realizar_manutencao_sick
from estoque.services.comunicado_service import ComunicadoService
from .models import (
    Comunicado,
    ComunicadoLeitura,
    Solicitacao,
    Transferencia,
    Emprestimo,
)


def notificacoes_context(request):

    if not request.user.is_authenticated:
        return {}

    ComunicadoService.notificar_manutencoes_previstas()
    ComunicadoService.excluir_expirados()

    perfil = request.user.perfil

    # ---------------- COMUNICADOS ----------------

    lidos = ComunicadoLeitura.objects.filter(
        usuario=request.user,
        comunicado=OuterRef('pk')
    )

    comunicados_nao_lidos_qs = (

        Comunicado.objects

        .filter(
            ativo=True
        )

        .exclude(
            comunicadooculto__usuario=request.user
        )

        .filter(
            Q(expira_em__isnull=True) |
            Q(expira_em__gt=timezone.now())
        )

        .filter(
            Q(enviar_para_todos=True) |
            Q(usuarios=request.user)
        )

        .annotate(
            lido=Exists(lidos)
        )

        .filter(
            lido=False
        )

        .distinct()
    )

    ultimo_comunicado_nao_lido = comunicados_nao_lidos_qs.order_by('-criado_em').first()

    comunicados_nao_lidos = (
        comunicados_nao_lidos_qs
        .count()
    )

    # ---------------- SOLICITAÇÕES ----------------

    solicitacoes_pendentes = 0

    if perfil.role == 'admin':

        solicitacoes_pendentes = (
            Solicitacao.objects
            .filter(status='PENDENTE')
            .count()
        )

    # ---------------- SEPARAÇÃO ----------------

    separacoes_pendentes = (
        Transferencia.objects
        .filter(
            regional_origem__in=perfil.regionais.all(),
            status='PENDENTE'
        )
        .count()
    )

    # ---------------- RECEBIMENTOS ----------------

    transferencias_pendentes = (
        Transferencia.objects
        .filter(
            regional_destino__in=perfil.regionais.all(),
            status='EM_TRANSITO'
        )
        .count()
    )

    # ---------------- EMPRÉSTIMOS ----------------

    emprestimos_recebimento = (
        Emprestimo.objects
        .filter(
            regional_destino__in=perfil.regionais.all(),
            status='AGUARDANDO_RECEBIMENTO'
        )
        .count()
    )

    emprestimos_devolucao = (
        Emprestimo.objects
        .filter(
            regional_destino__in=perfil.regionais.all(),
            status='EMPRESTADO'
        )
        .count()
    )

    emprestimos_confirmacao = (
        Emprestimo.objects
        .filter(
            regional_origem__in=perfil.regionais.all(),
            status='AGUARDANDO_CONFIRMACAO_DEVOLUCAO'
        )
        .count()
    )
    # ---------------- TOTAL EMPRÉSTIMOS ----------------

    emprestimos_pendentes = (
            emprestimos_recebimento +
            emprestimos_devolucao +
            emprestimos_confirmacao
    )

    # ---------------- TOTAL MENU ----------------

    notificacoes_pendentes = (
            solicitacoes_pendentes +
            separacoes_pendentes +
            transferencias_pendentes +
            emprestimos_pendentes
    )

    return {

        'comunicados_nao_lidos': comunicados_nao_lidos,
        'ultimo_comunicado_nao_lido': ultimo_comunicado_nao_lido,
        'notificacoes_pendentes': notificacoes_pendentes,
        'solicitacoes_pendentes': solicitacoes_pendentes,
        'separacoes_pendentes': separacoes_pendentes,
        'transferencias_pendentes': transferencias_pendentes,
        'emprestimos_recebimento': emprestimos_recebimento,
        'emprestimos_devolucao': emprestimos_devolucao,
        'emprestimos_confirmacao': emprestimos_confirmacao,
        'emprestimos_pendentes': emprestimos_pendentes,
    }

def permissoes_especiais(request):
    if request.user.is_authenticated:
        return {
            'pode_realizar_manutencao_sick':
                pode_realizar_manutencao_sick(request.user)
        }

    return {
        'pode_realizar_manutencao_sick': False
    }
