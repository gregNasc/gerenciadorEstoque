from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from estoque.permissions import pode_realizar_manutencao_sick
from estoque.policies.compras import ComprasAccessPolicy
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
        compras_restrito = ComprasAccessPolicy.restrito(request.user)
        perfil = request.user.perfil
        return {
            'pode_realizar_manutencao_sick':
                pode_realizar_manutencao_sick(request.user),
            'pode_visualizar_valores':
                ComprasAccessPolicy.pode_visualizar_valores(request.user),
            'pode_editar_precos':
                ComprasAccessPolicy.pode_editar_precos(request.user),
            'pode_gerenciar_fornecedores':
                ComprasAccessPolicy.pode_gerenciar_fornecedores(request.user),
            'compras_restrito': compras_restrito,
            'pode_visualizar_saude_estoque': bool(
                not compras_restrito
                and (
                    request.user.is_superuser
                    or perfil.is_admin
                    or perfil.is_executivo_insumos
                )
            ),
        }

    return {
        'pode_realizar_manutencao_sick': False,
        'pode_visualizar_valores': False,
        'pode_editar_precos': False,
        'pode_gerenciar_fornecedores': False,
        'compras_restrito': False,
        'pode_visualizar_saude_estoque': False,
    }
