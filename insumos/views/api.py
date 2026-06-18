from django.contrib.auth.decorators import login_required
from django.db.models.functions import TruncMonth
from decimal import Decimal
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import (Q, Sum, F)
from insumos.models import ConsumoInsumo
from insumos.models import (Inventario, ChecklistDiario, SolicitacaoInsumo, Insumo)
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from insumos.models import Insumo
from insumos.forms import (InsumoForm, CadastroInsumoForm)
from insumos.services.movimentacao_service import MovimentacaoService


@login_required
def estoque_insumos(request):

    perfil = request.user.perfil
    bases = perfil.regionais.all()
    estoque = []

    for base in bases:

        for insumo in Insumo.objects.filter(ativo=True).select_related('categoria'):

            saldo = MovimentacaoService.saldo(base, insumo)

            if saldo <= 0:
                continue

            estoque.append({
                'base': base,
                'insumo': insumo,
                'saldo': saldo,
                'minimo': insumo.estoque_minimo,
                'critico': saldo <= insumo.estoque_minimo
            })

    return render(request, 'insumos/estoque_insumos.html', {'estoque': estoque})

@login_required
def kpi_inventarios(request):

    perfil = request.user.perfil

    qs = Inventario.objects.all()

    if not perfil.is_admin:
        qs = qs.filter(base__in=perfil.regionais.all())

    data = {
        "planejados": qs.filter(status="PLANEJADO").count(),
        "andamento": qs.filter(status="EM_ANDAMENTO").count(),
        "finalizados": qs.filter(status="FINALIZADO").count(),
    }

    return JsonResponse(data)

@login_required
def consumo_por_base(request):

    data = (
        ConsumoInsumo.objects
        .values("inventario__base__nome")
        .annotate(total=Sum("valor_total"))
        .order_by("-total")
    )

    return JsonResponse(list(data), safe=False)

@login_required
def ranking_insumos(request):

    data = (
        ConsumoInsumo.objects
        .values("insumo__descricao")
        .annotate(total=Sum("quantidade"))
        .order_by("-total")[:10]
    )

    return JsonResponse(list(data), safe=False)

@login_required
def consumo_por_mes(request):

    data = (
        ConsumoInsumo.objects
        .annotate(mes=TruncMonth("criado_em"))
        .values("mes")
        .annotate(total=Sum("valor_total"))
        .order_by("mes")
    )

    return JsonResponse(list(data), safe=False)

@login_required
def lista_insumos(request):

    insumos = Insumo.objects.select_related('categoria').order_by(
        'categoria__nome',
        'descricao'
    )

    categoria = request.GET.get('categoria')

    if categoria:
        insumos = insumos.filter(categoria_id=categoria)

    return render(request, 'insumos/lista_insumos.html', {
        'insumos': insumos
    })

@login_required
def cadastrar_insumo(request):

    if request.method == 'POST':

        form = CadastroInsumoForm(request.POST, user=request.user)

        if form.is_valid():

            base = form.cleaned_data['base']
            insumo = form.cleaned_data['insumo']
            quantidade = form.cleaned_data['quantidade']

            MovimentacaoService.entrada(
                base=base,
                insumo=insumo,
                quantidade=quantidade,
                usuario=request.user,
                valor_unitario=Decimal('0.00'),
                observacao='Cadastro inicial de estoque'
            )

            messages.success(request, 'Entrada registrada com sucesso.')

            return redirect('insumos:cadastrar_insumos')

    else:

        form = CadastroInsumoForm(user=request.user)

    return render(request, 'insumos/cadastrar_insumos.html', {'form': form})

@login_required
def editar_insumo(request, pk):

    insumo = get_object_or_404(Insumo, pk=pk)

    if request.method == 'POST':
        form = InsumoForm(request.POST, instance=insumo)

        if form.is_valid():
            form.save()
            messages.success(request, 'Insumo atualizado com sucesso.')
            return redirect('insumos:lista_insumos')

    else:
        form = InsumoForm(instance=insumo)

    return render(
        request,
        'insumos/cadastrar_insumo.html',
        {
            'form': form,
            'insumo': insumo
        }
    )

@login_required
def insumos_por_categoria(request):

    categoria_id = request.GET.get('categoria')

    if not categoria_id:
        return JsonResponse({'insumos': []})

    insumos = (
        Insumo.objects
        .filter(
            categoria_id=categoria_id,
            ativo=True
        )
        .order_by('descricao')
        .values(
            'id',
            'descricao'
        )
    )

    return JsonResponse({
        'insumos': list(insumos)
    })

