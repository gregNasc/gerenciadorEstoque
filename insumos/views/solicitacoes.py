from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from insumos.forms import SolicitacaoInsumoForm
from insumos.models import Insumo, SolicitacaoInsumo
from insumos.services.solicitacao_service import SolicitacaoService


def _pode_decidir(user):
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and (perfil.is_admin or perfil.is_compras_insumos))


def _pode_acompanhar(user):
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and (
        perfil.is_admin or perfil.is_gestor or perfil.is_compras_insumos or
        perfil.is_financeiro_insumos
    ))


def _queryset_visivel(user):
    qs = SolicitacaoInsumo.objects.select_related(
        'base', 'solicitante', 'aprovado_por', 'em_compra_por'
    ).prefetch_related('itens__insumo')
    if _pode_decidir(user) or user.perfil.is_financeiro_insumos:
        return qs
    return qs.filter(solicitante=user)


@login_required
def lista_solicitacoes(request):
    if not _pode_acompanhar(request.user):
        raise PermissionDenied

    qs = _queryset_visivel(request.user)
    status = request.GET.get('status', '').strip().upper()
    busca = request.GET.get('q', '').strip()
    if status:
        qs = qs.filter(status=status)
    if busca:
        qs = qs.filter(
            Q(protocolo__icontains=busca) |
            Q(base__nome__icontains=busca) |
            Q(solicitante__first_name__icontains=busca) |
            Q(solicitante__last_name__icontains=busca) |
            Q(itens__insumo__descricao__icontains=busca)
        ).distinct()

    totais = _queryset_visivel(request.user).values('status').annotate(total=Count('id'))
    return render(request, 'insumos/solicitacoes/lista.html', {
        'solicitacoes': qs.order_by('-criado_em')[:200],
        'totais': {item['status']: item['total'] for item in totais},
        'status_choices': SolicitacaoInsumo.STATUS,
        'pode_decidir': _pode_decidir(request.user),
        'pode_solicitar': request.user.perfil.is_admin or request.user.perfil.is_gestor,
        'busca': busca,
        'status_atual': status,
    })


@login_required
def criar_solicitacao(request):
    if not (request.user.perfil.is_admin or request.user.perfil.is_gestor):
        raise PermissionDenied

    form = SolicitacaoInsumoForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        insumos_ids = request.POST.getlist('insumo')
        quantidades = request.POST.getlist('quantidade')
        observacoes = request.POST.getlist('observacao_item')
        itens_por_insumo = {}
        erros = []
        insumos = {
            str(item.pk): item
            for item in Insumo.objects.filter(pk__in=insumos_ids, ativo=True)
        }
        for indice, insumo_id in enumerate(insumos_ids):
            if not insumo_id and not (quantidades[indice] if indice < len(quantidades) else ''):
                continue
            insumo = insumos.get(insumo_id)
            try:
                quantidade = Decimal(quantidades[indice])
            except (InvalidOperation, IndexError, TypeError):
                quantidade = Decimal('0')
            if not insumo or quantidade <= 0:
                erros.append(_('Selecione um insumo e informe uma quantidade maior que zero.'))
                continue
            observacao = observacoes[indice].strip() if indice < len(observacoes) else ''
            if insumo.pk in itens_por_insumo:
                item_existente = itens_por_insumo[insumo.pk]
                item_existente['quantidade'] += quantidade
                if observacao and observacao not in item_existente['observacao']:
                    item_existente['observacao'] = '; '.join(filter(None, [
                        item_existente['observacao'], observacao,
                    ]))
            else:
                itens_por_insumo[insumo.pk] = {
                    'insumo': insumo,
                    'quantidade': quantidade,
                    'observacao': observacao,
                }

        itens = list(itens_por_insumo.values())
        if not itens:
            erros.append(_('Inclua ao menos um item válido na solicitação.'))
        if not erros:
            solicitacao = SolicitacaoService.criar_solicitacao(
                base=form.cleaned_data['base'],
                solicitante=request.user,
                justificativa=form.cleaned_data['justificativa'],
                prioridade=form.cleaned_data['prioridade'],
                itens=itens,
            )
            messages.success(request, _('Solicitação de insumos enviada para Compras.'))
            return redirect('insumos:detalhe_solicitacao', pk=solicitacao.pk)
        for erro in erros:
            messages.error(request, erro)

    return render(request, 'insumos/solicitacoes/criar.html', {
        'form': form,
        'insumos': Insumo.objects.filter(ativo=True).select_related('categoria').order_by(
            'categoria__nome', 'descricao'
        ),
    })


@login_required
def detalhe_solicitacao(request, pk):
    if not _pode_acompanhar(request.user):
        raise PermissionDenied
    solicitacao = get_object_or_404(_queryset_visivel(request.user), pk=pk)
    return render(request, 'insumos/solicitacoes/detalhe.html', {
        'solicitacao': solicitacao,
        'pode_decidir': _pode_decidir(request.user),
    })


@login_required
def decidir_solicitacao(request, pk):
    if not _pode_decidir(request.user) or request.method != 'POST':
        raise PermissionDenied
    solicitacao = get_object_or_404(_queryset_visivel(request.user), pk=pk)
    acao = request.POST.get('acao', '')
    observacao = request.POST.get('observacao', '').strip()
    try:
        if acao == 'aprovar':
            SolicitacaoService.aprovar(
                solicitacao=solicitacao,
                usuario=request.user,
                observacao=observacao,
            )
            messages.success(request, _('Solicitação aprovada.'))
        elif acao == 'reprovar':
            SolicitacaoService.reprovar(
                solicitacao=solicitacao,
                usuario=request.user,
                motivo=observacao,
            )
            messages.success(request, _('Solicitação reprovada.'))
        elif acao == 'comprar':
            SolicitacaoService.colocar_em_compra(
                solicitacao=solicitacao,
                usuario=request.user,
                observacao=observacao,
            )
            messages.success(request, _('Solicitação encaminhada para compra.'))
        else:
            messages.error(request, _('Ação inválida.'))
    except ValueError as erro:
        messages.error(request, str(erro))
    return redirect('insumos:detalhe_solicitacao', pk=solicitacao.pk)
