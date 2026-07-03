from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from insumos.models import SolicitacaoInsumo, ConsumoInsumo


@login_required
def dashboard_planejamento(request):
    perfil = request.user.perfil
    if not (perfil.is_admin or perfil.is_planejamento_insumos or perfil.is_executivo_insumos):
        return render(request, "403.html")

    solicitacoes = SolicitacaoInsumo.objects.all()
    context = {
        "solicitacoes_pendentes": solicitacoes.filter(status="PENDENTE").count(),
        "solicitacoes_em_compra": solicitacoes.filter(status="EM_COMPRA").count(),
        "solicitacoes_finalizadas": solicitacoes.filter(status="FINALIZADA").count(),
        "consumo_total": ConsumoInsumo.objects.count(),
    }

    return render(request, "insumos/dashboard/planejamento/dashboard_planejamento.html", context)
