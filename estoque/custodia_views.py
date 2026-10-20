from pathlib import Path
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render

from estoque.forms_custodia import (
    ColaboradorForm,
    CustodiaForm,
    DevolucaoCustodiaForm,
)
from estoque.models import (
    Colaborador,
    Custodia,
    DevolucaoCustodia,
    Equipamento,
    ItemDevolucaoCustodia,
    TermoDevolucaoCustodia,
    TermoEntregaCustodia,
)
from estoque.policies.colaboradores import ColaboradorAccessPolicy
from estoque.policies.custodias import CustodiaAccessPolicy
from estoque.services.termo_entrega_custodia_service import (
    TermoEntregaCustodiaService,
)
from estoque.services.custodia_devolucao_service import CustodiaDevolucaoService


logger = logging.getLogger(__name__)


@login_required
def lista_colaboradores(request):
    CustodiaAccessPolicy.exigir(request.user, CustodiaAccessPolicy.VIEW)
    colaboradores = ColaboradorAccessPolicy.colaboradores(
        request.user,
    ).select_related('empresa', 'base', 'usuario')
    busca = request.GET.get('q', '').strip()
    if busca:
        colaboradores = colaboradores.filter(
            Q(nome__icontains=busca)
            | Q(matricula__icontains=busca)
            | Q(usuario__username__icontains=busca)
        )
    return render(request, 'estoque/custodias/colaboradores_lista.html', {
        'colaboradores': colaboradores.order_by('empresa__nome', 'nome'),
        'busca': busca,
        'pode_gerenciar_custodias': CustodiaAccessPolicy.permite(
            request.user,
            CustodiaAccessPolicy.MANAGE,
        ),
    })


@login_required
def criar_colaborador(request):
    CustodiaAccessPolicy.exigir(request.user, CustodiaAccessPolicy.MANAGE)
    form = ColaboradorForm(
        request.POST or None,
        actor=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        colaborador = form.save()
        messages.success(request, f'Colaborador {colaborador.nome} cadastrado com sucesso.')
        proximo = request.POST.get('proximo', '').strip()
        if proximo == 'custodia':
            return redirect('estoque:criar_custodia')
        return redirect('estoque:lista_colaboradores')
    return render(request, 'estoque/custodias/colaborador_form.html', {
        'form': form,
        'titulo': 'Novo colaborador',
    })


@login_required
def editar_colaborador(request, colaborador_id):
    CustodiaAccessPolicy.exigir(request.user, CustodiaAccessPolicy.MANAGE)
    colaborador = get_object_or_404(
        ColaboradorAccessPolicy.colaboradores(
            request.user,
            action=ColaboradorAccessPolicy.MANAGE,
        ),
        pk=colaborador_id,
    )
    form = ColaboradorForm(
        request.POST or None,
        instance=colaborador,
        actor=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        colaborador = form.save()
        messages.success(request, f'Colaborador {colaborador.nome} atualizado.')
        return redirect('estoque:lista_colaboradores')
    return render(request, 'estoque/custodias/colaborador_form.html', {
        'form': form,
        'titulo': 'Editar colaborador',
        'colaborador': colaborador,
    })


@login_required
def lista_custodias(request):
    CustodiaAccessPolicy.exigir(request.user, CustodiaAccessPolicy.VIEW)
    custodias = CustodiaAccessPolicy.custodias(
        request.user,
    ).select_related('empresa', 'base', 'colaborador').prefetch_related('itens')
    status = request.GET.get('status', '').strip()
    busca = request.GET.get('q', '').strip()
    if status in Custodia.Status.values:
        custodias = custodias.filter(status=status)
    if busca:
        custodias = custodias.filter(
            Q(colaborador__nome__icontains=busca)
            | Q(colaborador__matricula__icontains=busca)
            | Q(itens__equipamento__patrimonio__icontains=busca)
            | Q(itens__equipamento__numero_serie__icontains=busca)
        ).distinct()
    return render(request, 'estoque/custodias/lista.html', {
        'custodias': custodias,
        'status_filtro': status,
        'busca': busca,
        'status_choices': Custodia.Status.choices,
        'pode_gerenciar_custodias': CustodiaAccessPolicy.permite(
            request.user,
            CustodiaAccessPolicy.MANAGE,
        ),
    })


@login_required
def criar_custodia(request):
    CustodiaAccessPolicy.exigir(request.user, CustodiaAccessPolicy.MANAGE)
    equipamento = None
    equipamento_id = request.GET.get('equipamento', '').strip()
    if equipamento_id.isdigit():
        empresas = CustodiaAccessPolicy.empresas(
            request.user,
            action=CustodiaAccessPolicy.MANAGE,
        )
        equipamento = Equipamento.objects.filter(
            pk=equipamento_id,
            regional__empresa__in=empresas,
        ).select_related(
            'regional__empresa', 'produto',
        ).first()
    form = CustodiaForm(
        request.POST or None,
        actor=request.user,
        equipamento_inicial=equipamento,
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            custodia = form.criar()
        try:
            TermoEntregaCustodiaService.gerar(
                custodia=custodia,
                usuario=request.user,
            )
        except ValidationError as exc:
            messages.warning(
                request,
                'A Custódia foi ativada, mas o termo não pôde ser gerado: '
                + '; '.join(exc.messages),
            )
            return redirect('estoque:detalhe_custodia', custodia_id=custodia.pk)
        except Exception:
            logger.exception('Falha ao gerar termo da Custódia %s.', custodia.pk)
            messages.warning(
                request,
                'A Custódia foi ativada, mas houve uma falha no armazenamento '
                'do termo. Use “Gerar termo” na tela de detalhes.',
            )
            return redirect('estoque:detalhe_custodia', custodia_id=custodia.pk)
        else:
            messages.success(
                request,
                f'Custódia #{custodia.pk} ativada e Termo de Entrega gerado.',
            )
            return redirect('estoque:detalhe_custodia', custodia_id=custodia.pk)
    return render(request, 'estoque/custodias/form.html', {
        'form': form,
        'equipamento_inicial': equipamento,
        'tem_colaboradores': form.fields['colaborador'].queryset.exists(),
    })


@login_required
def detalhe_custodia(request, custodia_id):
    CustodiaAccessPolicy.exigir(request.user, CustodiaAccessPolicy.VIEW)
    custodia = get_object_or_404(
        CustodiaAccessPolicy.custodias(request.user).select_related(
            'empresa', 'base', 'local_fisico', 'colaborador',
            'colaborador__usuario', 'registrado_por',
        ).prefetch_related('itens__equipamento__produto', 'itens__linha_movel'),
        pk=custodia_id,
    )
    return render(request, 'estoque/custodias/detalhe.html', {
        'custodia': custodia,
        'devolucoes': custodia.devolucoes.select_related(
            'responsavel_recebimento',
        ).prefetch_related('itens').order_by('-data_devolucao', '-pk'),
        'pode_gerenciar_custodias': CustodiaAccessPolicy.permite(
            request.user,
            CustodiaAccessPolicy.MANAGE,
        ),
    })


@login_required
def gerar_termo_entrega(request, custodia_id):
    CustodiaAccessPolicy.exigir(request.user, CustodiaAccessPolicy.MANAGE)
    if request.method != 'POST':
        return redirect('estoque:detalhe_custodia', custodia_id=custodia_id)
    custodia = get_object_or_404(
        CustodiaAccessPolicy.custodias(
            request.user,
            action=CustodiaAccessPolicy.MANAGE,
        ),
        pk=custodia_id,
    )
    try:
        TermoEntregaCustodiaService.gerar(custodia=custodia, usuario=request.user)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Termo de Entrega disponível.')
    return redirect('estoque:detalhe_custodia', custodia_id=custodia_id)


@login_required
def baixar_termo_entrega(request, custodia_id):
    CustodiaAccessPolicy.exigir(request.user, CustodiaAccessPolicy.VIEW)
    custodia = get_object_or_404(
        CustodiaAccessPolicy.custodias(request.user).select_related('termo_entrega'),
        pk=custodia_id,
    )
    termo = get_object_or_404(TermoEntregaCustodia, custodia=custodia)
    arquivo = termo.arquivo_pdf.open('rb')
    nome = Path(termo.arquivo_pdf.name).name or f'termo-custodia-{custodia.pk}.pdf'
    return FileResponse(arquivo, as_attachment=True, filename=nome)


@login_required
def devolver_custodia(request, custodia_id):
    CustodiaAccessPolicy.exigir(request.user, CustodiaAccessPolicy.MANAGE)
    custodia = get_object_or_404(
        CustodiaAccessPolicy.custodias(
            request.user,
            action=CustodiaAccessPolicy.MANAGE,
        ).select_related('empresa', 'base', 'colaborador'),
        pk=custodia_id,
    )
    itens_pendentes = list(custodia.itens.filter(
        vigente=True,
        devolvido_em__isnull=True,
    ).select_related('equipamento__produto', 'linha_movel'))
    form = DevolucaoCustodiaForm(
        request.POST or None,
        actor=request.user,
        custodia=custodia,
    )
    if request.method == 'POST' and form.is_valid():
        classificacoes = []
        for item in itens_pendentes:
            situacao = request.POST.get(f'situacao_{item.pk}', '').strip()
            condicao = request.POST.get(f'condicao_{item.pk}', '').strip()
            if situacao == ItemDevolucaoCustodia.Situacao.FALTANTE:
                condicao = Custodia.CondicaoGeral.NAO_INFORMADA
            classificacoes.append({
                'item_custodia': item,
                'situacao': situacao,
                'condicao_devolucao': condicao,
                'observacao': request.POST.get(f'observacao_{item.pk}', ''),
            })
        try:
            devolucao = CustodiaDevolucaoService.registrar(
                custodia=custodia,
                itens=classificacoes,
                motivo=form.cleaned_data['motivo'],
                responsavel_recebimento=form.cleaned_data['responsavel_recebimento'],
                registrado_por=request.user,
                data_devolucao=form.cleaned_data['data_devolucao'],
                observacao=form.cleaned_data['observacao'],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                f'Devolução #{devolucao.pk} registrada e termo gerado.',
            )
            return redirect('estoque:detalhe_custodia', custodia_id=custodia.pk)
    return render(request, 'estoque/custodias/devolucao_form.html', {
        'custodia': custodia,
        'itens_pendentes': itens_pendentes,
        'form': form,
        'situacao_choices': ItemDevolucaoCustodia.Situacao.choices,
        'condicao_choices': Custodia.CondicaoGeral.choices,
    })


@login_required
def baixar_termo_devolucao(request, devolucao_id):
    CustodiaAccessPolicy.exigir(request.user, CustodiaAccessPolicy.VIEW)
    devolucao = get_object_or_404(
        DevolucaoCustodia.objects.filter(
            custodia__in=CustodiaAccessPolicy.custodias(request.user),
        ),
        pk=devolucao_id,
    )
    termo = get_object_or_404(TermoDevolucaoCustodia, devolucao=devolucao)
    arquivo = termo.arquivo_pdf.open('rb')
    nome = Path(termo.arquivo_pdf.name).name or f'termo-devolucao-{devolucao.pk}.pdf'
    return FileResponse(arquivo, as_attachment=True, filename=nome)
