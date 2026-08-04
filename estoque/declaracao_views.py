from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import DeclaracaoCorreiosForm, DeclaracaoCorreiosItemFormSet, DeclaracaoEnderecoForm
from .models import DeclaracaoCorreios, Emprestimo, Transferencia
from .services.declaracao_correios_service import DeclaracaoCorreiosService


def _perfil(user):
    try:
        return user.perfil
    except ObjectDoesNotExist:
        return None


def _bases_operacao(declaracao):
    operacao = declaracao.transferencia or declaracao.emprestimo
    return operacao.regional_origem, operacao.regional_destino


def _exigir_acesso_operacao(user, operacao, *, editar=False):
    perfil = _perfil(user)
    if user.is_superuser or (perfil and perfil.is_admin):
        return
    if not perfil or perfil.empresa_id != operacao.regional_origem.empresa_id:
        raise PermissionDenied
    bases = [operacao.regional_origem] if editar else [operacao.regional_origem, operacao.regional_destino]
    if not perfil.regionais.filter(pk__in=[base.pk for base in bases]).exists():
        raise PermissionDenied


def _exigir_acesso(user, declaracao, *, editar=False):
    operacao = declaracao.transferencia or declaracao.emprestimo
    _exigir_acesso_operacao(user, operacao, editar=editar)


def _editar_declaracao(request, declaracao):
    _exigir_acesso(request.user, declaracao, editar=True)
    if declaracao.status != DeclaracaoCorreios.Status.RASCUNHO:
        return redirect('estoque:baixar_declaracao', declaracao_id=declaracao.pk)
    if request.method == 'POST':
        form = DeclaracaoCorreiosForm(request.POST, instance=declaracao)
        formset = DeclaracaoCorreiosItemFormSet(request.POST, instance=declaracao)
        form_remetente = DeclaracaoEnderecoForm(request.POST, prefix='remetente')
        form_destinatario = DeclaracaoEnderecoForm(request.POST, prefix='destinatario')
        if form.is_valid() and formset.is_valid() and form_remetente.is_valid() and form_destinatario.is_valid():
            declaracao = form.save(commit=False)
            declaracao.remetente = {
                **declaracao.remetente,
                **form_remetente.cleaned_data,
            }
            declaracao.destinatario = {
                **declaracao.destinatario,
                **form_destinatario.cleaned_data,
            }
            declaracao.save()
            formset.save()
            messages.success(request, 'Rascunho da declaração salvo.')
            return redirect('estoque:declaracao_detalhe', declaracao_id=declaracao.pk)
    else:
        form = DeclaracaoCorreiosForm(instance=declaracao)
        formset = DeclaracaoCorreiosItemFormSet(instance=declaracao)
        form_remetente = DeclaracaoEnderecoForm(initial=declaracao.remetente, prefix='remetente')
        form_destinatario = DeclaracaoEnderecoForm(initial=declaracao.destinatario, prefix='destinatario')
    return render(request, 'estoque/declaracoes/formulario.html', {
        'declaracao': declaracao,
        'form': form,
        'formset': formset,
        'form_remetente': form_remetente,
        'form_destinatario': form_destinatario,
        'versoes': DeclaracaoCorreios.objects.filter(
            transferencia=declaracao.transferencia,
            emprestimo=declaracao.emprestimo,
        ).order_by('-versao'),
    })


@login_required
def declaracao_transferencia(request, transferencia_id):
    transferencia = get_object_or_404(
        Transferencia.objects.select_related('regional_origem__empresa', 'regional_destino'),
        pk=transferencia_id,
    )
    _exigir_acesso_operacao(request.user, transferencia, editar=True)
    declaracao = DeclaracaoCorreiosService.criar_rascunho(
        usuario=request.user,
        transferencia=transferencia,
    )
    return _editar_declaracao(request, declaracao)


@login_required
def declaracao_emprestimo(request, emprestimo_id):
    emprestimo = get_object_or_404(
        Emprestimo.objects.select_related('regional_origem__empresa', 'regional_destino'),
        pk=emprestimo_id,
    )
    _exigir_acesso_operacao(request.user, emprestimo, editar=True)
    declaracao = DeclaracaoCorreiosService.criar_rascunho(
        usuario=request.user,
        emprestimo=emprestimo,
    )
    return _editar_declaracao(request, declaracao)


@login_required
def declaracao_detalhe(request, declaracao_id):
    declaracao = get_object_or_404(DeclaracaoCorreios, pk=declaracao_id)
    return _editar_declaracao(request, declaracao)


@login_required
@require_POST
def emitir_declaracao(request, declaracao_id):
    declaracao = get_object_or_404(DeclaracaoCorreios, pk=declaracao_id)
    _exigir_acesso(request.user, declaracao, editar=True)
    try:
        DeclaracaoCorreiosService.emitir_pdf(declaracao, request.user)
    except ValidationError as exc:
        for erro in exc.messages:
            messages.error(request, erro)
        return redirect('estoque:declaracao_detalhe', declaracao_id=declaracao.pk)
    messages.success(request, 'Declaração emitida e preservada com sucesso.')
    return redirect('estoque:baixar_declaracao', declaracao_id=declaracao.pk)


@login_required
def baixar_declaracao(request, declaracao_id):
    declaracao = get_object_or_404(DeclaracaoCorreios, pk=declaracao_id)
    _exigir_acesso(request.user, declaracao)
    if not declaracao.arquivo:
        return redirect('estoque:declaracao_detalhe', declaracao_id=declaracao.pk)
    return FileResponse(
        declaracao.arquivo.open('rb'),
        as_attachment=True,
        filename=declaracao.arquivo.name.rsplit('/', 1)[-1],
        content_type='application/pdf',
    )


@login_required
@require_POST
def substituir_declaracao(request, declaracao_id):
    declaracao = get_object_or_404(DeclaracaoCorreios, pk=declaracao_id)
    _exigir_acesso(request.user, declaracao, editar=True)
    nova = DeclaracaoCorreiosService.substituir(declaracao, {}, request.user)
    messages.info(request, f'Versão {nova.versao} criada sem alterar o documento anterior.')
    return redirect('estoque:declaracao_detalhe', declaracao_id=nova.pk)
