from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Sum
from insumos.models import ConsumoInsumo, Insumo
from insumos.permissions import Perms


@login_required
def dashboard_financeiro(request):
    perfil = request.user.perfil

    if not (
        perfil.is_admin or
        perfil.is_financeiro_insumos or
        perfil.is_executivo_insumos or
        request.user.has_perm(Perms.full(Perms.VISUALIZAR_CUSTOS))
    ):
        return render(request, "403.html")

    insumos = Insumo.objects.all()
    context = {
        "valor_total_estoque": insumos.aggregate(
            total=Sum("valor_medio")
        )["total"] or 0,

        "total_consumo": ConsumoInsumo.objects.aggregate(
            total=Sum("valor_total")
        )["total"] or 0,
    }

    return render(request, "insumos/dashboard/financeiro/dashboard_financeiro.html", context)
