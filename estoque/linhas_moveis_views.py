from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from estoque.forms_linhas_moveis import (
    CredenciaisLinhaMovelForm,
    LinhaMovelForm,
    OperadoraMovelForm,
)
from estoque.models import HistoricoLinhaMovel, LinhaMovel, OperadoraMovel
from estoque.policies.linhas_moveis import LinhasMoveisAccessPolicy
from estoque.services.linhas_moveis_service import (
    CredenciaisLinhaMovelService,
    LinhasMoveisService,
)


def _form_errors(request, form):
    for errors in form.errors.values():
        for error in errors:
            messages.error(request, error)


@login_required
def lista_linhas_moveis(request):
    LinhasMoveisAccessPolicy.exigir(request.user, LinhasMoveisAccessPolicy.VIEW)
    linhas = LinhasMoveisAccessPolicy.linhas(request.user).select_related(
        'empresa', 'base', 'operadora', 'usuario_responsavel',
    )
    empresas = LinhasMoveisAccessPolicy.empresas(request.user).order_by('nome')
    bases = LinhasMoveisAccessPolicy.bases(request.user)

    busca = request.GET.get('q', '').strip()
    empresa_id = request.GET.get('empresa', '').strip()
    base_id = request.GET.get('base', '').strip()
    status = request.GET.get('status', '').strip()
    if busca:
        linhas = linhas.filter(
            Q(numero_normalizado__icontains=busca)
            | Q(iccid__icontains=busca)
            | Q(operadora__nome__icontains=busca)
        )
    if empresa_id.isdigit():
        linhas = linhas.filter(empresa_id=empresa_id)
        bases = bases.filter(empresa_id=empresa_id)
    if base_id.isdigit():
        linhas = linhas.filter(base_id=base_id)
    if status in LinhaMovel.Status.values:
        linhas = linhas.filter(status=status)

    pagina = Paginator(linhas.order_by('empresa__nome', 'base__nome', 'numero_normalizado'), 30)
    return render(request, 'estoque/linhas_moveis/lista.html', {
        'pagina': pagina.get_page(request.GET.get('page')),
        'empresas': empresas,
        'bases': bases,
        'status_choices': LinhaMovel.Status.choices,
        'filtros': {
            'q': busca,
            'empresa': empresa_id,
            'base': base_id,
            'status': status,
        },
        'pode_gerenciar': (
            LinhasMoveisAccessPolicy.permite(
                request.user, LinhasMoveisAccessPolicy.MANAGE,
            )
            and LinhasMoveisAccessPolicy.empresas(
                request.user,
                action=LinhasMoveisAccessPolicy.MANAGE,
            ).exists()
        ),
        'pode_ver_credenciais': LinhasMoveisAccessPolicy.permite(
            request.user, LinhasMoveisAccessPolicy.VIEW_SECRETS,
        ),
    })


@login_required
@transaction.atomic
def criar_linha_movel(request):
    LinhasMoveisAccessPolicy.exigir(request.user, LinhasMoveisAccessPolicy.MANAGE)
    if not LinhasMoveisAccessPolicy.empresas(
        request.user, action=LinhasMoveisAccessPolicy.MANAGE,
    ).exists():
        raise PermissionDenied('Nenhuma empresa com conectividade móvel está disponível.')
    form = LinhaMovelForm(
        request.POST or None,
        user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        linha = form.save(commit=False)
        linha.criado_por = request.user
        linha.save()
        HistoricoLinhaMovel.objects.create(
            empresa=linha.empresa,
            linha=linha,
            evento=HistoricoLinhaMovel.Evento.CADASTRO,
            autor=request.user,
            metadados={'base_id': linha.base_id, 'operadora_id': linha.operadora_id},
        )
        messages.success(request, 'Linha móvel cadastrada com sucesso.')
        return redirect('estoque:lista_linhas_moveis')
    if request.method == 'POST':
        _form_errors(request, form)
    return render(request, 'estoque/linhas_moveis/form.html', {
        'form': form,
        'titulo': 'Nova linha móvel',
        'linha': None,
    })


@login_required
@transaction.atomic
def editar_linha_movel(request, linha_id):
    LinhasMoveisAccessPolicy.exigir(request.user, LinhasMoveisAccessPolicy.MANAGE)
    linha = LinhasMoveisAccessPolicy.obter_linha(
        request.user,
        linha_id,
        action=LinhasMoveisAccessPolicy.MANAGE,
        for_update=request.method == 'POST',
    )
    anteriores = {
        campo: getattr(linha, campo)
        for campo in (
            'base_id', 'numero_normalizado', 'operadora_id',
            'usuario_responsavel_id', 'responsavel_nome', 'iccid', 'observacao',
        )
    }
    form = LinhaMovelForm(
        request.POST or None,
        instance=linha,
        user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        linha = form.save()
        alterados = [
            campo for campo, valor in anteriores.items()
            if getattr(linha, campo) != valor
        ]
        if alterados:
            HistoricoLinhaMovel.objects.create(
                empresa=linha.empresa,
                linha=linha,
                evento=HistoricoLinhaMovel.Evento.ALTERACAO,
                autor=request.user,
                metadados={'campos_alterados': alterados},
            )
        messages.success(request, 'Linha móvel atualizada com sucesso.')
        return redirect('estoque:lista_linhas_moveis')
    if request.method == 'POST':
        _form_errors(request, form)
    return render(request, 'estoque/linhas_moveis/form.html', {
        'form': form,
        'titulo': 'Editar linha móvel',
        'linha': linha,
    })


@login_required
@require_POST
def inativar_linha_movel(request, linha_id):
    try:
        LinhasMoveisService.inativar(
            usuario=request.user,
            linha_id=linha_id,
            motivo=request.POST.get('motivo'),
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Linha móvel inativada com sucesso.')
    return redirect('estoque:lista_linhas_moveis')


@login_required
@require_POST
def reativar_linha_movel(request, linha_id):
    try:
        LinhasMoveisService.reativar(usuario=request.user, linha_id=linha_id)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Linha móvel reativada com sucesso.')
    return redirect('estoque:lista_linhas_moveis')


@login_required
@transaction.atomic
def operadoras_moveis(request, operadora_id=None):
    LinhasMoveisAccessPolicy.exigir(request.user, LinhasMoveisAccessPolicy.MANAGE)
    operadora = None
    if operadora_id is not None:
        try:
            operadora = LinhasMoveisAccessPolicy.operadoras(
                request.user,
                action=LinhasMoveisAccessPolicy.MANAGE,
                queryset=OperadoraMovel.objects.select_for_update(),
            ).get(pk=operadora_id)
        except OperadoraMovel.DoesNotExist as exc:
            raise PermissionDenied('Operadora inexistente ou fora do escopo.') from exc
    form = OperadoraMovelForm(
        request.POST or None,
        instance=operadora,
        user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(
            request,
            'Operadora atualizada com sucesso.' if operadora else 'Operadora cadastrada com sucesso.',
        )
        return redirect('estoque:operadoras_moveis')
    if request.method == 'POST':
        _form_errors(request, form)
    return render(request, 'estoque/linhas_moveis/operadoras.html', {
        'form': form,
        'operadora_editada': operadora,
        'operadoras': LinhasMoveisAccessPolicy.operadoras(
            request.user,
            action=LinhasMoveisAccessPolicy.MANAGE,
        ).select_related('empresa').order_by('empresa__nome', 'nome'),
    })


@login_required
@require_POST
def alternar_operadora_movel(request, operadora_id):
    try:
        operadora = LinhasMoveisAccessPolicy.operadoras(
            request.user,
            action=LinhasMoveisAccessPolicy.MANAGE,
        ).get(pk=operadora_id)
    except OperadoraMovel.DoesNotExist as exc:
        raise PermissionDenied('Operadora inexistente ou fora do escopo.') from exc
    operadora.ativa = not operadora.ativa
    operadora.save(update_fields=('ativa', 'atualizado_em'))
    messages.success(request, 'Status da operadora atualizado com sucesso.')
    return redirect('estoque:operadoras_moveis')


@login_required
def credenciais_linha_movel(request, linha_id):
    LinhasMoveisAccessPolicy.exigir(
        request.user,
        LinhasMoveisAccessPolicy.VIEW_SECRETS,
    )
    linha = LinhasMoveisAccessPolicy.obter_linha(
        request.user,
        linha_id,
        action=LinhasMoveisAccessPolicy.MANAGE,
    )
    form = CredenciaisLinhaMovelForm(request.POST or None)
    chaves_configuradas = bool(settings.LINHAS_MOVEIS_CREDENTIAL_KEYS)
    if request.method == 'POST' and not chaves_configuradas:
        messages.error(
            request,
            'LINHAS_MOVEIS_CREDENTIAL_KEYS deve ser configurada no ambiente para operar PIN/PUK.',
        )
    elif request.method == 'POST' and form.is_valid():
        try:
            CredenciaisLinhaMovelService.salvar(
                usuario=request.user,
                linha_id=linha.pk,
                pin=form.cleaned_data['pin'],
                pin2=form.cleaned_data['pin2'],
                puk=form.cleaned_data['puk'],
                puk2=form.cleaned_data['puk2'],
            )
        except (ImproperlyConfigured, ValidationError, PermissionDenied) as exc:
            messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        else:
            messages.success(request, 'Credenciais protegidas atualizadas com sucesso.')
            return redirect('estoque:lista_linhas_moveis')
    if request.method == 'POST' and chaves_configuradas:
        _form_errors(request, form)
    return render(request, 'estoque/linhas_moveis/credenciais.html', {
        'form': form,
        'linha': linha,
        'mascaradas': CredenciaisLinhaMovelService.mascaradas(
            usuario=request.user,
            linha_id=linha.pk,
        ),
        'chaves_configuradas': chaves_configuradas,
    })
