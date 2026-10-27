from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from insumos.forms import SolicitacaoInsumoForm
from insumos.models import (
    Insumo,
    ItemSolicitacaoInsumo,
    MovimentacaoInsumo,
    SaldoInsumoBase,
    SolicitacaoInsumo,
)
from insumos.policies import InsumosTenantPolicy
from insumos.services.solicitacao_service import SolicitacaoService


def _pode_decidir(user):
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and (perfil.is_admin or perfil.is_compras_insumos))


def _pode_acompanhar(user):
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and (
        perfil.is_admin or perfil.is_gestor or perfil.is_operador or
        perfil.is_compras_insumos or perfil.is_financeiro_insumos
    ))


def _pode_solicitar(user):
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and (perfil.is_gestor or perfil.is_operador))


def _ids_insumos_disponiveis(base):
    from compras.models import CodigoCatalogo

    ids = set(SaldoInsumoBase.objects.filter(
        base=base,
    ).values_list('insumo_id', flat=True))
    ids.update(MovimentacaoInsumo.objects.filter(
        base=base,
    ).values_list('insumo_id', flat=True))
    ids.update(CodigoCatalogo.objects.filter(
        empresa=base.empresa,
        insumo_id__isnull=False,
        ativo=True,
    ).values_list('insumo_id', flat=True))
    return ids


def _catalogo_solicitacao(base):
    from compras.models import CatalogoProdutoEmpresa

    insumos = list(Insumo.objects.filter(
        pk__in=_ids_insumos_disponiveis(base),
        ativo=True,
    ).select_related('categoria').order_by('categoria__nome', 'descricao'))
    equipamentos = CatalogoProdutoEmpresa.objects.filter(
        empresa=base.empresa,
        ativo=True,
        produto__ativo=True,
    ).select_related('produto').order_by(
        'produto__categoria', 'produto__descricao',
    )
    return {
        ItemSolicitacaoInsumo.Tipo.INSUMO: [
            {
                'id': item.pk,
                'nome': item.descricao,
                'categoria': item.categoria.nome,
                'unidade': item.unidade_medida,
            }
            for item in insumos
            if item.natureza != Insumo.Natureza.EPI
        ],
        ItemSolicitacaoInsumo.Tipo.EPI: [
            {
                'id': item.pk,
                'nome': item.descricao,
                'categoria': item.categoria.nome,
                'unidade': item.unidade_medida,
            }
            for item in insumos
            if item.natureza == Insumo.Natureza.EPI
        ],
        ItemSolicitacaoInsumo.Tipo.EQUIPAMENTO: [
            {
                'id': catalogo.produto_id,
                'nome': catalogo.produto.descricao,
                'categoria': catalogo.produto.categoria,
                'unidade': catalogo.produto.unidade_medida,
            }
            for catalogo in equipamentos
        ],
    }


def _itens_solicitacao_post(request, base):
    from compras.models import CatalogoProdutoEmpresa

    tokens = list(dict.fromkeys(request.POST.getlist('item_token')))
    if not tokens:
        raise ValueError(_('Inclua ao menos um item válido na solicitação.'))
    if len(tokens) > 50:
        raise ValueError(_('Uma solicitação pode conter no máximo 50 itens.'))

    insumos_ids = _ids_insumos_disponiveis(base)
    produtos_ids = set(CatalogoProdutoEmpresa.objects.filter(
        empresa=base.empresa,
        ativo=True,
        produto__ativo=True,
    ).values_list('produto_id', flat=True))
    tipos_validos = set(ItemSolicitacaoInsumo.Tipo.values)
    chaves_catalogo = set()
    itens = []

    for token in tokens:
        if not token or len(token) > 40 or not all(
            caractere.isalnum() or caractere in '_-'
            for caractere in token
        ):
            raise ValueError(_('Identificador de item inválido.'))
        tipo = request.POST.get(f'tipo_item_{token}', '').strip().upper()
        if tipo not in tipos_validos:
            raise ValueError(_('Selecione um tipo de item válido.'))
        try:
            quantidade = Decimal(request.POST.get(f'quantidade_{token}', ''))
        except (InvalidOperation, TypeError):
            quantidade = Decimal('0')
        if quantidade <= 0:
            raise ValueError(_('Informe uma quantidade maior que zero.'))

        dados = {
            'tipo': tipo,
            'quantidade': quantidade,
            'observacao': request.POST.get(f'observacao_{token}', '').strip(),
            'especificacao': request.POST.get(f'especificacao_{token}', '').strip(),
            'justificativa_item': request.POST.get(
                f'justificativa_item_{token}', '',
            ).strip(),
            'anexo': request.FILES.get(f'anexo_item_{token}'),
        }

        if tipo in {
            ItemSolicitacaoInsumo.Tipo.INSUMO,
            ItemSolicitacaoInsumo.Tipo.EPI,
        }:
            referencia = request.POST.get(f'referencia_item_{token}', '')
            if not referencia.isdigit() or int(referencia) not in insumos_ids:
                raise ValueError(_('O item não pertence ao catálogo desta Base.'))
            insumo = Insumo.objects.filter(pk=referencia, ativo=True).first()
            natureza_esperada = (
                Insumo.Natureza.EPI
                if tipo == ItemSolicitacaoInsumo.Tipo.EPI else None
            )
            if not insumo or (
                natureza_esperada and insumo.natureza != natureza_esperada
            ) or (
                tipo == ItemSolicitacaoInsumo.Tipo.INSUMO
                and insumo.natureza == Insumo.Natureza.EPI
            ):
                raise ValueError(_('O item não pertence ao tipo selecionado.'))
            chave = (tipo, insumo.pk)
            if chave in chaves_catalogo:
                raise ValueError(_('O mesmo item foi incluído mais de uma vez.'))
            chaves_catalogo.add(chave)
            dados['insumo'] = insumo
        elif tipo == ItemSolicitacaoInsumo.Tipo.EQUIPAMENTO:
            referencia = request.POST.get(f'referencia_item_{token}', '')
            if not referencia.isdigit() or int(referencia) not in produtos_ids:
                raise ValueError(
                    _('O equipamento não pertence ao catálogo desta empresa.')
                )
            from estoque.models import Produto
            produto = Produto.objects.filter(pk=referencia, ativo=True).first()
            if not produto:
                raise ValueError(
                    _('O equipamento não pertence ao catálogo desta empresa.')
                )
            chave = (tipo, produto.pk)
            if chave in chaves_catalogo:
                raise ValueError(_('O mesmo item foi incluído mais de uma vez.'))
            chaves_catalogo.add(chave)
            dados['produto_equipamento'] = produto
        else:
            dados['descricao_novo_item'] = request.POST.get(
                f'descricao_novo_item_{token}', '',
            ).strip()
            if not dados['descricao_novo_item']:
                raise ValueError(_('Descreva o item que ainda não está cadastrado.'))
            if not dados['justificativa_item']:
                raise ValueError(_('Informe por que o novo item é necessário.'))

        itens.append(dados)
    return itens


def _pode_ver_detalhes_administrativos(user):
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and (
        perfil.is_admin or perfil.is_compras_insumos or
        perfil.is_financeiro_insumos
    ))


def _queryset_visivel(user, *, action=InsumosTenantPolicy.VIEW):
    qs = SolicitacaoInsumo.objects.select_related(
        'base', 'solicitante', 'aprovado_por', 'em_compra_por'
    ).prefetch_related(
        'itens__insumo__categoria',
        'itens__produto_equipamento',
        'itens__resolvido_insumo__categoria',
        'itens__resolvido_produto',
        'eventos__autor',
    )
    qs = InsumosTenantPolicy.requests(user, qs, action=action)
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
            Q(itens__insumo__descricao__icontains=busca) |
            Q(itens__produto_equipamento__descricao__icontains=busca) |
            Q(itens__descricao_novo_item__icontains=busca)
        ).distinct()

    totais = _queryset_visivel(request.user).values('status').annotate(total=Count('id'))
    return render(request, 'insumos/solicitacoes/lista.html', {
        'solicitacoes': qs.order_by('-criado_em')[:200],
        'totais': {item['status']: item['total'] for item in totais},
        'status_choices': SolicitacaoInsumo.STATUS,
        'pode_decidir': _pode_decidir(request.user),
        'pode_solicitar': _pode_solicitar(request.user),
        'pode_ver_detalhes_administrativos': (
            _pode_ver_detalhes_administrativos(request.user)
        ),
        'busca': busca,
        'status_atual': status,
    })


@login_required
def criar_solicitacao(request):
    if not _pode_solicitar(request.user):
        raise PermissionDenied

    form = SolicitacaoInsumoForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            itens = _itens_solicitacao_post(
                request,
                form.cleaned_data['base'],
            )
            solicitacao = SolicitacaoService.criar_solicitacao(
                base=form.cleaned_data['base'],
                solicitante=request.user,
                justificativa=form.cleaned_data['justificativa'],
                prioridade=form.cleaned_data['prioridade'],
                itens=itens,
            )
            messages.success(request, _('Solicitação enviada para Compras.'))
            return redirect('insumos:detalhe_solicitacao', pk=solicitacao.pk)
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        except ValueError as erro:
            messages.error(request, str(erro))

    bases_form = list(form.fields['base'].queryset.select_related('empresa'))
    return render(request, 'insumos/solicitacoes/criar.html', {
        'form': form,
        'catalogo_por_base': {
            str(base.pk): _catalogo_solicitacao(base)
            for base in bases_form
        },
        'tipos_item': ItemSolicitacaoInsumo.Tipo.choices,
    })


@login_required
def detalhe_solicitacao(request, pk):
    if not _pode_acompanhar(request.user):
        raise PermissionDenied
    solicitacao = get_object_or_404(_queryset_visivel(request.user), pk=pk)
    pode_decidir = _pode_decidir(request.user)
    return render(request, 'insumos/solicitacoes/detalhe.html', {
        'solicitacao': solicitacao,
        'pode_decidir': pode_decidir,
        'catalogo_resolucao': (
            _catalogo_solicitacao(solicitacao.base) if pode_decidir else {}
        ),
        'aguarda_recebimento': solicitacao.status in {
            'PEDIDO_REALIZADO', 'EM_COMPRA',
        },
        'pode_atender': solicitacao.status == 'RECEBIDA',
        'pode_ver_detalhes_administrativos': (
            _pode_ver_detalhes_administrativos(request.user)
        ),
    })


@login_required
def resolver_novo_item(request, pk, item_id):
    if not _pode_decidir(request.user) or request.method != 'POST':
        raise PermissionDenied
    solicitacao = get_object_or_404(
        _queryset_visivel(request.user, action=InsumosTenantPolicy.APPROVE),
        pk=pk,
    )
    item = get_object_or_404(
        ItemSolicitacaoInsumo.objects.select_related('solicitacao__base__empresa'),
        pk=item_id,
        solicitacao=solicitacao,
        tipo=ItemSolicitacaoInsumo.Tipo.NOVO_ITEM,
    )
    tipo = request.POST.get('tipo_resolucao', '').strip().upper()
    referencia = request.POST.get('referencia', '').strip()
    try:
        if not referencia.isdigit():
            raise ValueError(_('Selecione uma referência de catálogo válida.'))
        if tipo in {'INSUMO', 'EPI'}:
            insumo = get_object_or_404(Insumo.objects.filter(ativo=True), pk=referencia)
            SolicitacaoService.resolver_novo_item(
                item=item,
                usuario=request.user,
                insumo=insumo,
                observacao=request.POST.get('observacao', ''),
            )
        elif tipo == 'EQUIPAMENTO':
            from estoque.models import Produto
            produto = get_object_or_404(Produto.objects.filter(ativo=True), pk=referencia)
            SolicitacaoService.resolver_novo_item(
                item=item,
                usuario=request.user,
                produto=produto,
                observacao=request.POST.get('observacao', ''),
            )
        else:
            raise ValueError(_('Selecione o tipo da referência de catálogo.'))
    except ValueError as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, _('Novo item vinculado ao catálogo autorizado.'))
    return redirect('insumos:detalhe_solicitacao', pk=solicitacao.pk)


@login_required
def baixar_anexo_item(request, pk, item_id):
    if not _pode_acompanhar(request.user):
        raise PermissionDenied
    solicitacao = get_object_or_404(_queryset_visivel(request.user), pk=pk)
    item = get_object_or_404(
        ItemSolicitacaoInsumo,
        pk=item_id,
        solicitacao=solicitacao,
    )
    if not item.anexo:
        raise Http404
    extensao = Path(item.anexo.name).suffix.lower()
    nome = f'anexo-{solicitacao.protocolo}-item-{item.pk}{extensao}'
    return FileResponse(item.anexo.open('rb'), as_attachment=True, filename=nome)


@login_required
def decidir_solicitacao(request, pk):
    if not _pode_decidir(request.user) or request.method != 'POST':
        raise PermissionDenied
    solicitacao = get_object_or_404(
        _queryset_visivel(request.user, action=InsumosTenantPolicy.APPROVE),
        pk=pk,
    )
    acao = request.POST.get('acao', '')
    observacao = request.POST.get('observacao', '').strip()
    try:
        if acao == 'receber_compras':
            SolicitacaoService.receber_compras(
                solicitacao=solicitacao,
                usuario=request.user,
                observacao=observacao,
            )
            messages.success(request, _('Solicitação recebida por Compras.'))
        elif acao == 'iniciar_analise':
            SolicitacaoService.iniciar_analise(
                solicitacao=solicitacao,
                usuario=request.user,
                observacao=observacao,
            )
            messages.success(request, _('Análise iniciada.'))
        elif acao == 'aprovar':
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
            messages.success(request, _('Pedido realizado e registrado.'))
        elif acao == 'receber_material':
            SolicitacaoService.registrar_recebimento(
                solicitacao=solicitacao,
                usuario=request.user,
                observacao=observacao,
            )
            messages.success(request, _('Recebimento registrado.'))
        elif acao == 'finalizar':
            SolicitacaoService.finalizar(
                solicitacao=solicitacao,
                usuario=request.user,
                observacao=observacao,
            )
            messages.success(request, _('Solicitação finalizada.'))
        else:
            messages.error(request, _('Ação inválida.'))
    except ValueError as erro:
        messages.error(request, str(erro))
    return redirect('insumos:detalhe_solicitacao', pk=solicitacao.pk)
