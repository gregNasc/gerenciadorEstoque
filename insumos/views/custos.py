from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Count, Max, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from estoque.models import Base

from insumos.forms import FornecedorInsumoForm, PrecoFornecedorInsumoForm
from insumos.models import (
    Cliente,
    FornecedorInsumo,
    HistoricoInsumo,
    Insumo,
    Inventario,
    OfertaPrecoOnline,
    PrecoFornecedorInsumo,
    PesquisaPrecoOnline,
)
from insumos.services.custo_service import CustoInsumoService
from insumos.services.preco_online_service import PrecoOnlineErro, PrecoOnlineService


def _pode_editar(user):
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and (perfil.is_admin or perfil.is_compras_insumos))


def _periodo_padrao(request):
    hoje = timezone.localdate()
    inicio = parse_date(request.GET.get('inicio', '')) or hoje.replace(day=1)
    fim = parse_date(request.GET.get('fim', '')) or hoje
    if fim < inicio:
        inicio, fim = fim, inicio
    return inicio, fim


def _id_opcional(valor):
    texto = str(valor or '').strip()
    return int(texto) if texto.isdigit() else None


@login_required
def dashboard_custos(request):
    if not CustoInsumoService.pode_visualizar(request.user):
        raise PermissionDenied

    inicio, fim = _periodo_padrao(request)
    cliente = Cliente.objects.filter(pk=_id_opcional(request.GET.get('cliente'))).first()
    loja = request.GET.get('loja', '').strip()
    tipo = request.GET.get('tipo', '').strip().upper()
    pessoas_texto = request.GET.get('pessoas', '').strip()
    pessoas = int(pessoas_texto) if pessoas_texto.isdigit() else None
    inventario_id = _id_opcional(request.GET.get('inventario'))
    base = Base.objects.filter(pk=_id_opcional(request.GET.get('base'))).first()

    qs = CustoInsumoService.filtrar(
        request.user,
        inicio=inicio,
        fim=fim,
        cliente=cliente,
        loja=loja,
        tipo=tipo,
        pessoas=pessoas,
        bases=[base] if base else None,
        inventario_id=inventario_id,
    )
    resumo = CustoInsumoService.resumo(qs)
    por_inventario = CustoInsumoService.por_inventario(qs, limite=25)
    por_cliente = CustoInsumoService.por_cliente(qs)
    por_tipo = CustoInsumoService.por_tipo(qs)
    mensal = CustoInsumoService.por_mes(qs)
    top_insumos = CustoInsumoService.top_insumos(qs)

    chart_inventarios = {
        'labels': [
            f"{item['inventario__cliente__sigla']} {item['inventario__loja']}"
            for item in por_inventario[:10]
        ],
        'values': [float(item['total']) for item in por_inventario[:10]],
    }
    chart_clientes = {
        'labels': [item['inventario__cliente__sigla'] for item in por_cliente],
        'values': [float(item['total']) for item in por_cliente],
    }
    chart_mensal = {
        'labels': [item['mes'].strftime('%m/%Y') for item in mensal],
        'values': [float(item['total']) for item in mensal],
    }
    chart_tipos = {
        'labels': [item['inventario__tipo'] or 'Sem tipo' for item in por_tipo],
        'values': [float(item['total']) for item in por_tipo],
    }
    chart_insumos = {
        'labels': [item['insumo__descricao'] for item in top_insumos],
        'values': [float(item['total']) for item in top_insumos],
    }
    total_insumos = Insumo.objects.filter(ativo=True).count()
    insumos_com_preco = Insumo.objects.filter(ativo=True, valor_medio__gt=0).count()
    cobertura_precos = round(insumos_com_preco * 100 / total_insumos, 1) if total_insumos else 100

    context = {
        'inicio': inicio,
        'fim': fim,
        'resumo': resumo,
        'valor_estoque': CustoInsumoService.valor_estoque_atual(
            request.user,
            bases=[base] if base else None,
        ),
        'por_inventario': por_inventario,
        'por_tipo': por_tipo,
        'top_insumos': top_insumos,
        'clientes': Cliente.objects.order_by('sigla'),
        'bases': Base.objects.exclude(nome__iexact='TODAS').order_by('nome'),
        'lojas': Inventario.objects.order_by('loja').values_list('loja', flat=True).distinct(),
        'tipos': Inventario.objects.exclude(tipo__isnull=True).exclude(tipo='').order_by('tipo').values_list('tipo', flat=True).distinct(),
        'inventarios': Inventario.objects.filter(data_inicio__range=(inicio, fim)).select_related(
            'cliente', 'base'
        ).order_by('cliente__sigla', 'loja'),
        'chart_inventarios': chart_inventarios,
        'chart_clientes': chart_clientes,
        'chart_mensal': chart_mensal,
        'chart_tipos': chart_tipos,
        'chart_insumos': chart_insumos,
        'total_insumos': total_insumos,
        'insumos_com_preco': insumos_com_preco,
        'cobertura_precos': cobertura_precos,
        'consumos_sem_custo': qs.filter(valor_unitario=0).count(),
        'pode_editar': _pode_editar(request.user),
    }
    return render(request, 'insumos/custos/dashboard_custos.html', context)


@login_required
def precos_insumos(request):
    if not CustoInsumoService.pode_visualizar(request.user):
        raise PermissionDenied

    editar_id = request.GET.get('editar') or request.POST.get('preco_id')
    instancia = PrecoFornecedorInsumo.objects.filter(pk=editar_id).first() if editar_id else None
    if request.method == 'POST':
        if not _pode_editar(request.user):
            raise PermissionDenied
        form = PrecoFornecedorInsumoForm(request.POST, instance=instancia)
        if form.is_valid():
            with transaction.atomic():
                preco = form.save(commit=False)
                preco.cadastrado_por = request.user
                preco.full_clean()
                preco.save()
                if form.cleaned_data.get('aplicar_como_custo'):
                    preco.insumo.valor_medio = preco.valor_unitario
                    preco.insumo.preco_referencia = preco
                    preco.insumo.save(update_fields=['valor_medio', 'preco_referencia'])
                HistoricoInsumo.objects.create(
                    tipo='PRECO',
                    usuario=request.user,
                    descricao=f'Preço atualizado para {preco.insumo.descricao}',
                    dados={
                        'insumo': preco.insumo.descricao,
                        'fornecedor': preco.fornecedor.nome,
                        'valor_unitario': str(preco.valor_unitario),
                        'custo_atual': bool(form.cleaned_data.get('aplicar_como_custo')),
                    },
                )
            messages.success(request, _('Preço unitário registrado com sucesso.'))
            return redirect('insumos:precos_insumos')
    else:
        form = PrecoFornecedorInsumoForm(instance=instancia)

    precos_base = PrecoFornecedorInsumo.objects.select_related(
        'insumo', 'fornecedor', 'cadastrado_por'
    )
    precos = precos_base.order_by('-vigente_desde', 'insumo__descricao')
    busca = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip().lower()
    if busca:
        precos = precos.filter(
            Q(insumo__descricao__icontains=busca) |
            Q(fornecedor__nome__icontains=busca)
        )
    if status == 'ativos':
        precos = precos.filter(ativo=True)
    elif status == 'inativos':
        precos = precos.filter(ativo=False)

    comparar_insumo_id = _id_opcional(request.GET.get('comparar_insumo'))
    comparar_insumo = Insumo.objects.filter(pk=comparar_insumo_id).first()
    comparacao_precos = []
    menor_preco = None
    if comparar_insumo:
        cotacoes = PrecoFornecedorInsumo.objects.filter(
            insumo=comparar_insumo,
            ativo=True,
        ).select_related('fornecedor').order_by(
            'fornecedor__nome', '-vigente_desde', '-criado_em'
        )
        por_fornecedor = {}
        for cotacao in cotacoes:
            por_fornecedor.setdefault(cotacao.fornecedor_id, cotacao)
        comparacao_precos = sorted(
            por_fornecedor.values(),
            key=lambda cotacao: (cotacao.valor_unitario, cotacao.fornecedor.nome),
        )
        if comparacao_precos:
            menor_preco = comparacao_precos[0].valor_unitario
    return render(request, 'insumos/custos/precos_insumos.html', {
        'form': form,
        'precos': precos[:200],
        'pode_editar': _pode_editar(request.user),
        'editando': instancia,
        'busca': busca,
        'status': status,
        'insumos': Insumo.objects.filter(ativo=True).order_by('descricao'),
        'comparar_insumo': comparar_insumo,
        'comparacao_precos': comparacao_precos,
        'menor_preco': menor_preco,
        'total_precos': precos_base.count(),
        'total_precos_ativos': precos_base.filter(ativo=True).count(),
        'total_insumos_cotados': precos_base.values('insumo_id').distinct().count(),
        'total_fornecedores_cotados': precos_base.values('fornecedor_id').distinct().count(),
    })


@login_required
def fornecedores_insumos(request):
    if not CustoInsumoService.pode_visualizar(request.user):
        raise PermissionDenied

    editar_id = request.GET.get('editar') or request.POST.get('fornecedor_id')
    instancia = FornecedorInsumo.objects.filter(pk=editar_id).first() if editar_id else None
    if request.method == 'POST':
        if not _pode_editar(request.user):
            raise PermissionDenied
        form = FornecedorInsumoForm(request.POST, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(request, _('Fornecedor salvo com sucesso.'))
            return redirect('insumos:fornecedores_insumos')
    else:
        form = FornecedorInsumoForm(instance=instancia)

    fornecedores_base = FornecedorInsumo.objects.annotate(
        itens=Count('precos__insumo', distinct=True),
        cotacoes=Count('precos'),
        menor_preco=Min('precos__valor_unitario', filter=Q(precos__ativo=True)),
        preco_medio=Avg('precos__valor_unitario', filter=Q(precos__ativo=True)),
        maior_preco=Max('precos__valor_unitario', filter=Q(precos__ativo=True)),
    )
    busca = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip().lower()
    fornecedores = fornecedores_base
    if busca:
        fornecedores = fornecedores.filter(
            Q(nome__icontains=busca) |
            Q(documento__icontains=busca) |
            Q(contato__icontains=busca) |
            Q(email__icontains=busca)
        )
    if status == 'ativos':
        fornecedores = fornecedores.filter(ativo=True)
    elif status == 'inativos':
        fornecedores = fornecedores.filter(ativo=False)
    fornecedores = fornecedores.order_by('nome')

    precos_recentes = PrecoFornecedorInsumo.objects.select_related(
        'fornecedor', 'insumo'
    ).filter(ativo=True).order_by('-vigente_desde')[:20]
    return render(request, 'insumos/custos/fornecedores_insumos.html', {
        'form': form,
        'fornecedores': fornecedores,
        'precos_recentes': precos_recentes,
        'pode_editar': _pode_editar(request.user),
        'editando': instancia,
        'busca': busca,
        'status': status,
        'total_fornecedores': FornecedorInsumo.objects.count(),
        'total_fornecedores_ativos': FornecedorInsumo.objects.filter(ativo=True).count(),
        'total_itens_cotados': PrecoFornecedorInsumo.objects.values(
            'insumo_id'
        ).distinct().count(),
        'total_cotacoes_ativas': PrecoFornecedorInsumo.objects.filter(ativo=True).count(),
    })


@login_required
def pesquisa_precos_online(request):
    if not CustoInsumoService.pode_visualizar(request.user):
        raise PermissionDenied

    insumo_id = _id_opcional(request.POST.get('insumo') or request.GET.get('insumo'))
    insumo = Insumo.objects.filter(pk=insumo_id, ativo=True).first()
    termo = (request.POST.get('termo') or request.GET.get('termo') or '').strip()
    try:
        quantidade = Decimal(request.POST.get('quantidade') or request.GET.get('quantidade') or '1')
    except InvalidOperation:
        quantidade = Decimal('1')
    if quantidade <= 0:
        quantidade = Decimal('1')

    if request.method == 'POST':
        if not _pode_editar(request.user):
            raise PermissionDenied
        if not insumo:
            messages.error(request, _('Selecione um insumo para pesquisar.'))
        else:
            try:
                PrecoOnlineService.pesquisar(
                    insumo=insumo,
                    termo=termo or insumo.descricao,
                    usuario=request.user,
                )
                messages.success(request, _('Pesquisa de preços atualizada.'))
                return redirect(
                    f"{reverse('insumos:pesquisa_precos_online')}?insumo={insumo.id}"
                    f"&quantidade={quantidade}&termo={termo or insumo.descricao}"
                )
            except PrecoOnlineErro as erro:
                messages.error(request, str(erro))

    pesquisa = None
    ofertas = OfertaPrecoOnline.objects.none()
    if insumo:
        pesquisa = PesquisaPrecoOnline.objects.filter(insumo=insumo).first()
        if pesquisa:
            ofertas = pesquisa.ofertas.select_related('insumo').order_by('preco_total', 'titulo')

    ofertas_lista = list(ofertas)
    menor = ofertas_lista[0].preco_total if ofertas_lista else Decimal('0')
    maior = max((oferta.preco_total for oferta in ofertas_lista), default=Decimal('0'))
    media = (
        sum((oferta.preco_total for oferta in ofertas_lista), Decimal('0')) / len(ofertas_lista)
        if ofertas_lista else Decimal('0')
    )
    economia = (maior - menor) * quantidade if ofertas_lista else Decimal('0')
    historico = list(
        OfertaPrecoOnline.objects.filter(insumo=insumo).order_by('-coletado_em')[:60]
    ) if insumo else []

    return render(request, 'insumos/custos/pesquisa_precos.html', {
        'insumos': Insumo.objects.filter(ativo=True).order_by('descricao'),
        'insumo_selecionado': insumo,
        'termo': termo or (insumo.descricao if insumo else ''),
        'quantidade': quantidade,
        'pesquisa': pesquisa,
        'ofertas': ofertas_lista,
        'menor': menor,
        'maior': maior,
        'media': media,
        'economia': economia,
        'pode_pesquisar': _pode_editar(request.user),
        'api_configurada': PrecoOnlineService.configurado(),
        'chart_ofertas': {
            'labels': [oferta.titulo[:35] for oferta in ofertas_lista[:12]],
            'values': [float(oferta.preco_total) for oferta in ofertas_lista[:12]],
        },
        'chart_historico': {
            'labels': [oferta.coletado_em.strftime('%d/%m %H:%M') for oferta in reversed(historico)],
            'values': [float(oferta.preco_total) for oferta in reversed(historico)],
        },
    })
