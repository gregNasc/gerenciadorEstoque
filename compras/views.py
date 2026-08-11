import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditorias.services.visibilidade_estoque_service import VisibilidadeEstoqueAuditoriaService
from compras.forms import AquisicaoForm, ItemAquisicaoForm, RemessaForm
from compras.models import Aquisicao, CodigoCatalogo, ItemRemessaCompra, RemessaCompra
from compras.policies import AquisicaoAccessPolicy
from compras.services import AquisicaoService, RemessaCompraService
from estoque.models import Base, Equipamento
from estoque.policies.compras import ComprasAccessPolicy
from insumos.models import SaldoInsumoBase


@login_required
def lista_aquisicoes(request):
    return render(request, 'compras/aquisicao_lista.html', {
        'aquisicoes': AquisicaoAccessPolicy.queryset(request.user).select_related(
            'empresa', 'fornecedor', 'cadastrado_por'
        ).prefetch_related('itens')[:250],
        'pode_gerenciar': AquisicaoAccessPolicy.pode_gerenciar(request.user),
    })


@login_required
def criar_aquisicao(request):
    if not AquisicaoAccessPolicy.pode_gerenciar(request.user):
        raise PermissionDenied
    form = AquisicaoForm(request.POST or None, request.FILES or None)
    item_form = ItemAquisicaoForm(request.POST or None)
    form.fields['empresa'].queryset = ComprasAccessPolicy.empresas(request.user)
    if request.method == 'POST' and form.is_valid() and item_form.is_valid():
        dados = form.cleaned_data.copy()
        empresa = dados.pop('empresa')
        fornecedor = dados.pop('fornecedor')
        item = item_form.cleaned_data
        try:
            aquisicao = AquisicaoService.criar(
                empresa=empresa, fornecedor=fornecedor, usuario=request.user,
                itens=[item], **dados,
            )
        except (ValidationError, PermissionDenied) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Aquisição cadastrada com rastreabilidade financeira.')
            return redirect('compras:aquisicao_detalhe', pk=aquisicao.pk)
    return render(request, 'compras/aquisicao_form.html', {'form': form, 'item_form': item_form})


@login_required
def detalhe_aquisicao(request, pk):
    aquisicao = get_object_or_404(
        AquisicaoAccessPolicy.queryset(request.user).select_related(
            'empresa', 'fornecedor', 'cadastrado_por', 'aprovado_por'
        ).prefetch_related('itens__produto', 'itens__insumo', 'eventos'),
        pk=pk,
    )
    return render(request, 'compras/aquisicao_detalhe.html', {
        'aquisicao': aquisicao,
        'pode_gerenciar': AquisicaoAccessPolicy.pode_gerenciar(request.user),
    })


@login_required
@require_POST
def aprovar_aquisicao(request, pk):
    aquisicao = get_object_or_404(AquisicaoAccessPolicy.queryset(request.user), pk=pk)
    try:
        AquisicaoService.aprovar(aquisicao, request.user)
        messages.success(request, 'Aquisição aprovada.')
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    return redirect('compras:aquisicao_detalhe', pk=pk)


@login_required
def documento_aquisicao(request, pk, tipo):
    aquisicao = get_object_or_404(AquisicaoAccessPolicy.queryset(request.user), pk=pk)
    campo = {'danfe': aquisicao.arquivo_danfe_pdf, 'xml': aquisicao.arquivo_xml_nfe}.get(tipo)
    if not campo:
        raise PermissionDenied('Documento inexistente ou não autorizado.')
    return FileResponse(campo.open('rb'), as_attachment=True, filename=campo.name.rsplit('/', 1)[-1])


@login_required
def lista_remessas(request):
    remessas = AquisicaoAccessPolicy.remessas(request.user).select_related(
        'empresa', 'base_origem', 'base_destino', 'aquisicao'
    ).prefetch_related('itens')
    return render(request, 'compras/remessa_lista.html', {
        'remessas': remessas[:250],
        'pode_criar': ComprasAccessPolicy.pode_criar_remessa(request.user),
    })


@login_required
def criar_remessa(request):
    if not ComprasAccessPolicy.pode_criar_remessa(request.user):
        raise PermissionDenied
    form = RemessaForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        dados = form.cleaned_data
        item = {
            'insumo': dados['insumo'], 'equipamento': dados['equipamento'],
            'item_aquisicao': dados['item_aquisicao'],
            'quantidade_prevista': dados['quantidade'],
            'custo_unitario_snapshot': dados['custo_unitario'],
        }
        try:
            remessa = RemessaCompraService.criar(
                empresa=dados['empresa'], fluxo=dados['fluxo'],
                aquisicao=dados['aquisicao'], base_origem=dados['base_origem'],
                base_destino=dados['base_destino'], usuario=request.user,
                previsao_chegada=dados['previsao_chegada'], observacao=dados['observacao'],
                itens=[item],
            )
        except (ValidationError, PermissionDenied, ValueError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f'Remessa {remessa.protocolo} criada.')
            return redirect('compras:remessa_detalhe', pk=remessa.pk)
    return render(request, 'compras/remessa_form.html', {'form': form})


@login_required
def detalhe_remessa(request, pk):
    remessa = get_object_or_404(
        AquisicaoAccessPolicy.remessas(request.user).select_related(
            'empresa', 'base_origem', 'base_destino', 'aquisicao', 'criada_por'
        ).prefetch_related('itens__insumo', 'itens__equipamento__produto', 'recebimentos__linhas'),
        pk=pk,
    )
    return render(request, 'compras/remessa_detalhe.html', {
        'remessa': remessa,
        'pode_enviar': ComprasAccessPolicy.pode_criar_remessa(request.user),
        'pode_confirmar': AquisicaoAccessPolicy.pode_confirmar(request.user, remessa),
        'idempotency_key': uuid.uuid4(),
    })


@login_required
@require_POST
def enviar_remessa(request, pk):
    remessa = get_object_or_404(AquisicaoAccessPolicy.remessas(request.user), pk=pk)
    try:
        RemessaCompraService.enviar(remessa, request.user, request.POST.get('codigo_rastreio', ''))
        messages.success(request, 'Remessa enviada para conferência do destino.')
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    return redirect('compras:remessa_detalhe', pk=pk)


@login_required
@require_POST
def confirmar_remessa(request, pk):
    remessa = get_object_or_404(AquisicaoAccessPolicy.remessas(request.user), pk=pk)
    linhas = []
    for item in remessa.itens.all():
        linhas.append({
            'item_id': item.pk,
            'quantidade_recebida': request.POST.get(f'recebida_{item.pk}', 0),
            'quantidade_avariada': request.POST.get(f'avariada_{item.pk}', 0),
            'quantidade_faltante': request.POST.get(f'faltante_{item.pk}', 0),
            'observacao': request.POST.get(f'observacao_{item.pk}', ''),
        })
    try:
        RemessaCompraService.confirmar(
            remessa=remessa, usuario=request.user,
            idempotency_key=request.POST.get('idempotency_key'), linhas=linhas,
            finalizar=request.POST.get('finalizar') == '1',
            observacao=request.POST.get('observacao', ''),
        )
        messages.success(request, 'Conferência registrada sem duplicar entradas.')
    except (ValidationError, PermissionDenied, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect('compras:remessa_detalhe', pk=pk)


@login_required
def valores_insumos(request):
    if not ComprasAccessPolicy.pode_visualizar_valores(request.user):
        raise PermissionDenied
    saldos = SaldoInsumoBase.objects.select_related('base__empresa', 'insumo__categoria')
    bases = ComprasAccessPolicy.bases(request.user)
    if not request.user.perfil.is_admin:
        saldos = saldos.filter(base__in=bases)
    base_id = request.GET.get('base')
    if base_id and base_id.isdigit():
        saldos = saldos.filter(base_id=base_id)
    valor = ExpressionWrapper(F('saldo') * F('custo_medio'), output_field=DecimalField())
    return render(request, 'compras/valores_insumos.html', {
        'saldos': saldos.order_by('base__nome', 'insumo__descricao')[:1000],
        'bases': bases,
        'total': saldos.aggregate(
            total=Coalesce(Sum(valor), Value(Decimal('0')))
        )['total'],
        'skus': saldos.values('base_id', 'insumo_id').distinct().count(),
        'sem_preco': saldos.filter(custo_medio=0).count(),
    })


@login_required
def valores_equipamentos(request):
    if not ComprasAccessPolicy.pode_visualizar_valores(request.user):
        raise PermissionDenied
    equipamentos = VisibilidadeEstoqueAuditoriaService.ocultar_equipamentos(
        Equipamento.objects.select_related('produto', 'regional__empresa', 'fornecedor')
    )
    bases = ComprasAccessPolicy.bases(request.user)
    if not request.user.perfil.is_admin:
        equipamentos = equipamentos.filter(regional__in=bases)
    base_id = request.GET.get('base')
    if base_id and base_id.isdigit():
        equipamentos = equipamentos.filter(regional_id=base_id)
    valor = Coalesce('custo_aquisicao', 'preco_referencia', 0, output_field=DecimalField())
    categorias = {
        'operacional': equipamentos.filter(finalidade='OPERACIONAL', status__in=['ATIVO', 'EM_USO']).aggregate(v=Sum(valor))['v'] or 0,
        'administrativo': equipamentos.filter(finalidade='ADMINISTRATIVO').aggregate(v=Sum(valor))['v'] or 0,
        'indisponivel': equipamentos.filter(status__in=['SICK', 'MANUTENCAO']).aggregate(v=Sum(valor))['v'] or 0,
        'transito': equipamentos.filter(status='EM_TRANSITO').aggregate(v=Sum(valor))['v'] or 0,
        'baixados': equipamentos.filter(status__in=['BAIXA', 'INATIVO']).aggregate(v=Sum(valor))['v'] or 0,
    }
    return render(request, 'compras/valores_equipamentos.html', {
        'equipamentos': equipamentos.order_by('regional__nome', 'produto__descricao')[:1000],
        'bases': bases,
        'total': equipamentos.aggregate(v=Sum(valor))['v'] or 0,
        'sem_preco': equipamentos.filter(custo_aquisicao=None, preco_referencia=None).count(),
        'categorias_valor': categorias,
        'pode_editar': ComprasAccessPolicy.pode_editar_precos(request.user),
    })


@login_required
def resolver_codigo(request):
    codigo = request.GET.get('codigo', '').strip()
    if not codigo:
        return JsonResponse({'erro': 'Informe o código.'}, status=400)
    qs = CodigoCatalogo.objects.filter(codigo=codigo, ativo=True).select_related('produto', 'insumo', 'empresa')
    perfil = request.user.perfil
    if not perfil.is_admin:
        empresas_ids = list(ComprasAccessPolicy.empresas(request.user).values_list('id', flat=True))
        if perfil.empresa_id:
            empresas_ids.append(perfil.empresa_id)
        qs = qs.filter(empresa_id__in=set(empresas_ids))
    registro = qs.first()
    if not registro:
        return JsonResponse({'encontrado': False, 'codigo': codigo}, status=404)
    objeto = registro.produto or registro.insumo
    return JsonResponse({
        'encontrado': True, 'codigo': codigo, 'tipo_codigo': registro.tipo,
        'fator_conversao': str(registro.fator_conversao),
        'tipo_item': 'EQUIPAMENTO' if registro.produto_id else 'INSUMO',
        'id': objeto.pk, 'descricao': objeto.descricao,
    })
