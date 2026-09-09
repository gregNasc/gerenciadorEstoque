from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from insumos.models import (Inventario, ChecklistDiario, SolicitacaoInsumo, Insumo)
from insumos.policies import InsumosTenantPolicy
from insumos.utils import secure_queryset_insumos


@login_required
def dashboard_base(request):

    inventarios = InsumosTenantPolicy.inventories(
        request.user, Inventario.objects.all()
    )
    checklists = InsumosTenantPolicy.checklists(
        request.user, ChecklistDiario.objects.all()
    )
    solicitacoes = secure_queryset_insumos(SolicitacaoInsumo.objects.all(), request.user, campo_base='base')
    insumos = Insumo.objects.filter(ativo=True)

    context = {
        "inventarios_andamento": inventarios.filter(status="EM_ANDAMENTO").count(),
        "inventarios_planejados": inventarios.filter(status="PLANEJADO").count(),
        "checklists_abertos": checklists.filter(status="ABERTO").count(),
        "checklists_execucao": checklists.filter(status="EM_EXECUCAO").count(),
        "solicitacoes_pendentes": solicitacoes.filter(status="PENDENTE").count(),
        "insumos_criticos": insumos.filter(estoque_minimo__gt=0).count(),
    }

    return render(request, "insumos/dashboard/base/dashboard_base.html", context)
