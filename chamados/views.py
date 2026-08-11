from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from chamados.forms import ChamadoForm, ChamadoMensagemForm, ChamadoStatusForm
from chamados.models import Chamado, ChamadoAnexo
from chamados.policies import ChamadoAccessPolicy
from chamados.services import ChamadoService
from ordens_servico.models import OrdemServico


def _filtrar(request, queryset):
    status = request.GET.get('status', '').strip()
    prioridade = request.GET.get('prioridade', '').strip()
    base = request.GET.get('base', '').strip()
    busca = request.GET.get('q', '').strip()
    if status:
        queryset = queryset.filter(status=status)
    if prioridade:
        queryset = queryset.filter(prioridade=prioridade)
    if base.isdigit():
        queryset = queryset.filter(base_id=base)
    if busca:
        queryset = queryset.filter(
            Q(protocolo__icontains=busca)
            | Q(titulo__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(loja__icontains=busca)
        )
    return queryset


def _excel_seguro(valor):
    if isinstance(valor, str) and valor.startswith(('=', '+', '-', '@')):
        return f"'{valor}"
    return valor


@login_required
def lista(request):
    qs = _filtrar(
        request,
        ChamadoAccessPolicy.queryset(request.user).select_related(
            'base', 'empresa', 'categoria', 'aberto_por', 'atendente'
        ),
    )
    return render(request, 'chamados/lista.html', {
        'chamados': qs[:300],
        'bases': ChamadoAccessPolicy.bases(request.user),
        'status_choices': Chamado.Status.choices,
        'prioridade_choices': Chamado.Prioridade.choices,
        'pode_atender': ChamadoAccessPolicy.pode_atender(request.user),
    })


@login_required
def criar(request):
    form = ChamadoForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            chamado = ChamadoService.abrir(usuario=request.user, **form.cleaned_data)
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f'CHAMADO {chamado.protocolo} ABERTO COM SUCESSO.')
            return redirect('chamados:detalhe', pk=chamado.pk)
    return render(request, 'chamados/form.html', {'form': form})


@login_required
def detalhe(request, pk):
    chamado = get_object_or_404(
        ChamadoAccessPolicy.queryset(request.user).select_related(
            'empresa', 'base', 'categoria', 'inventario__cliente', 'aberto_por', 'atendente'
        ).prefetch_related('mensagens__autor', 'mensagens__anexos', 'eventos__usuario'),
        pk=pk,
    )
    pode_atender = ChamadoAccessPolicy.pode_atender(request.user)
    mensagens_qs = chamado.mensagens.all()
    if not pode_atender:
        mensagens_qs = mensagens_qs.filter(nota_interna=False)
    status_permitidos = ChamadoService.status_permitidos(chamado, request.user)
    ordens = OrdemServico.objects.filter(chamado_referencia=chamado.protocolo).order_by('-aberto_em')
    return render(request, 'chamados/detalhe.html', {
        'chamado': chamado,
        'mensagens_chamado': mensagens_qs,
        'mensagem_form': ChamadoMensagemForm(),
        'status_form': ChamadoStatusForm(
            status_permitidos=status_permitidos,
            initial={'resolucao': chamado.resolucao},
        ),
        'status_permitidos': status_permitidos,
        'pode_atender': pode_atender,
        'pode_interagir': ChamadoAccessPolicy.pode_interagir(request.user, chamado),
        'ordens': ordens,
    })


@login_required
@require_POST
def assumir(request, pk):
    chamado = get_object_or_404(ChamadoAccessPolicy.queryset(request.user), pk=pk)
    try:
        ChamadoService.assumir(chamado, request.user)
        messages.success(request, 'CHAMADO ASSUMIDO COM SUCESSO.')
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, str(exc))
    return redirect('chamados:detalhe', pk=pk)


@login_required
@require_POST
def mensagem(request, pk):
    chamado = get_object_or_404(ChamadoAccessPolicy.queryset(request.user), pk=pk)
    form = ChamadoMensagemForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            ChamadoService.adicionar_mensagem(
                chamado=chamado,
                usuario=request.user,
                texto=form.cleaned_data['texto'],
                nota_interna=form.cleaned_data['nota_interna'],
                anexo=form.cleaned_data['anexo'],
            )
            messages.success(request, 'MENSAGEM REGISTRADA.')
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'NÃO FOI POSSÍVEL REGISTRAR A MENSAGEM.')
    return redirect('chamados:detalhe', pk=pk)


@login_required
@require_POST
def alterar_status(request, pk):
    chamado = get_object_or_404(ChamadoAccessPolicy.queryset(request.user), pk=pk)
    permitidos = ChamadoService.status_permitidos(chamado, request.user)
    form = ChamadoStatusForm(request.POST, status_permitidos=permitidos)
    if form.is_valid():
        try:
            ChamadoService.alterar_status(
                chamado, request.user, form.cleaned_data['status'], form.cleaned_data['resolucao']
            )
            messages.success(request, 'STATUS ATUALIZADO.')
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'VERIFIQUE O STATUS E A RESOLUÇÃO INFORMADOS.')
    return redirect('chamados:detalhe', pk=pk)


@login_required
def baixar_anexo(request, pk):
    anexo = get_object_or_404(ChamadoAnexo.objects.select_related('chamado'), pk=pk)
    if not ChamadoAccessPolicy.pode_ver(request.user, anexo.chamado):
        raise PermissionDenied
    if anexo.mensagem and anexo.mensagem.nota_interna and not ChamadoAccessPolicy.pode_atender(request.user):
        raise PermissionDenied
    return FileResponse(anexo.arquivo.open('rb'), as_attachment=True, filename=anexo.nome_original)


@login_required
def dashboard(request):
    qs = ChamadoAccessPolicy.queryset(request.user)
    agora = timezone.now()
    terminais = [Chamado.Status.RESOLVIDO, Chamado.Status.FECHADO, Chamado.Status.CANCELADO]
    por_status = list(qs.values('status').annotate(total=Count('id')).order_by('status'))
    por_categoria = list(
        qs.values('categoria__nome').annotate(total=Count('id')).order_by('-total')[:8]
    )
    por_base = list(qs.values('base__nome').annotate(total=Count('id')).order_by('-total')[:8])
    return render(request, 'chamados/dashboard.html', {
        'total': qs.count(),
        'abertos': qs.exclude(status__in=terminais).count(),
        'resolvidos': qs.filter(status__in=[Chamado.Status.RESOLVIDO, Chamado.Status.FECHADO]).count(),
        'sla_vencido': qs.filter(prazo_sla_em__lt=agora).exclude(status__in=terminais).count(),
        'por_status': por_status,
        'por_categoria': por_categoria,
        'por_base': por_base,
    })


@login_required
def exportar(request):
    if not (
        ChamadoAccessPolicy.pode_atender(request.user)
        or request.user.has_perm('chamados.exportar_chamados')
    ):
        raise PermissionDenied
    qs = _filtrar(
        request,
        ChamadoAccessPolicy.queryset(request.user).select_related(
            'base', 'categoria', 'aberto_por', 'atendente'
        ),
    )
    workbook = Workbook()
    planilha = workbook.active
    planilha.title = 'CHAMADOS'
    planilha.append([
        'PROTOCOLO', 'BASE', 'LOJA', 'CATEGORIA', 'TÍTULO', 'PRIORIDADE', 'STATUS',
        'ABERTO POR', 'ATENDENTE', 'ABERTURA', 'RESOLUÇÃO',
    ])
    for chamado in qs.iterator():
        planilha.append([_excel_seguro(valor) for valor in [
            chamado.protocolo,
            chamado.base.nome,
            chamado.loja,
            chamado.categoria.nome,
            chamado.titulo,
            chamado.get_prioridade_display(),
            chamado.get_status_display(),
            chamado.aberto_por.get_full_name() or chamado.aberto_por.get_username(),
            (chamado.atendente.get_full_name() or chamado.atendente.get_username()) if chamado.atendente else '',
            timezone.localtime(chamado.aberto_em).replace(tzinfo=None),
            chamado.resolucao,
        ]])
    arquivo = BytesIO()
    workbook.save(arquivo)
    arquivo.seek(0)
    return FileResponse(
        arquivo,
        as_attachment=True,
        filename=f'chamados-{timezone.localdate().isoformat()}.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
