from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Sum
from insumos.models import ConsumoInsumo, Insumo
from insumos.permissions import Perms


@login_required
def dashboard_financeiro(request):

    if not request.user.has_perm(Perms.VISUALIZAR_CUSTOS):
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