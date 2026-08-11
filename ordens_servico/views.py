from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from estoque.policies.compras import ComprasAccessPolicy
from ordens_servico.models import OrdemServico, OrdemServicoAssinatura
from ordens_servico.policies import OrdemServicoAccessPolicy
from ordens_servico.services import OrdemServicoService


@login_required
def lista(request):
    ordens = OrdemServicoAccessPolicy.queryset(request.user).select_related(
        'empresa', 'base_origem', 'base_destino', 'solicitante'
    )
    status = request.GET.get('status', '').strip()
    tipo = request.GET.get('tipo', '').strip()
    if status in OrdemServico.Status.values:
        ordens = ordens.filter(status=status)
    if tipo in OrdemServico.Tipo.values:
        ordens = ordens.filter(tipo=tipo)
    return render(request, 'ordens_servico/lista.html', {
        'ordens': ordens[:250],
        'status_choices': OrdemServico.Status.choices,
        'tipo_choices': OrdemServico.Tipo.choices,
        'filtros': {'status': status, 'tipo': tipo},
    })


@login_required
def detalhe(request, pk):
    ordem = get_object_or_404(
        OrdemServicoAccessPolicy.queryset(request.user).select_related(
            'empresa', 'base_responsavel', 'base_origem', 'base_destino',
            'solicitante', 'responsavel_operacional', 'autorizador', 'recebedor',
        ).prefetch_related('linhas', 'assinaturas__usuario', 'eventos__usuario'),
        pk=pk,
    )
    return render(request, 'ordens_servico/detalhe.html', {
        'ordem': ordem,
        'tipos_assinatura': OrdemServicoAssinatura.Tipo.choices,
        'pode_autorizar': OrdemServicoAccessPolicy.pode_autorizar(request.user),
        'pode_ver_valores': ComprasAccessPolicy.pode_visualizar_valores(request.user),
    })


@login_required
@require_POST
def assinar(request, pk):
    ordem = get_object_or_404(OrdemServicoAccessPolicy.queryset(request.user), pk=pk)
    try:
        OrdemServicoService.assinar(
            ordem=ordem,
            usuario=request.user,
            senha=request.POST.get('senha', ''),
            tipo=request.POST.get('tipo', ''),
            ip=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
        messages.success(request, 'O.S. assinada digitalmente. A senha não foi armazenada.')
    except (ValidationError, PermissionDenied) as exc:
        texto = ' '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        messages.error(request, texto)
    return redirect('ordens_servico:detalhe', pk=ordem.pk)


@login_required
def imprimir(request, pk):
    ordem = get_object_or_404(OrdemServicoAccessPolicy.queryset(request.user), pk=pk)
    return render(request, 'ordens_servico/imprimir.html', {
        'ordem': ordem,
        'pode_ver_valores': ComprasAccessPolicy.pode_visualizar_valores(request.user),
    })


@login_required
def pdf(request, pk):
    ordem = get_object_or_404(
        OrdemServicoAccessPolicy.queryset(request.user).prefetch_related(
            'linhas', 'assinaturas__usuario'
        ),
        pk=pk,
    )
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=ordem.numero,
    )
    styles = getSampleStyleSheet()
    elementos = [
        Paragraph(f'<b>ORDEM DE SERVIÇO {ordem.numero}</b>', styles['Title']),
        Paragraph(
            f'{ordem.get_tipo_display()} · {ordem.get_status_display()} · '
            f'{ordem.get_prioridade_display()}',
            styles['Heading2'],
        ),
        Spacer(1, 6 * mm),
    ]
    dados = [
        ['Empresa', ordem.empresa.nome],
        ['Origem', ordem.base_origem.nome if ordem.base_origem else '-'],
        ['Destino', ordem.base_destino.nome if ordem.base_destino else '-'],
        ['Solicitante', ordem.solicitante.get_full_name() or ordem.solicitante.get_username()],
        ['Abertura', ordem.aberto_em.strftime('%d/%m/%Y %H:%M')],
        ['Motivo', ordem.motivo],
    ]
    tabela = Table(dados, colWidths=[38 * mm, 137 * mm])
    tabela.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), .4, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#eef2f7')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    elementos += [tabela, Spacer(1, 6 * mm), Paragraph('<b>Itens</b>', styles['Heading2'])]
    linhas = [['Descrição', 'Qtd.', 'Patrimônio', 'Série', 'Origem', 'Destino']]
    for linha in ordem.linhas.all():
        linhas.append([
            linha.descricao,
            str(linha.quantidade),
            linha.patrimonio or '-',
            linha.numero_serie or '-',
            linha.origem or '-',
            linha.destino or '-',
        ])
    itens = Table(linhas, repeatRows=1, colWidths=[48*mm, 13*mm, 27*mm, 30*mm, 28*mm, 28*mm])
    itens.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), .35, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elementos += [itens, Spacer(1, 6 * mm), Paragraph('<b>Assinaturas digitais</b>', styles['Heading2'])]
    assinaturas = [['Tipo', 'Usuário', 'Data/hora', 'Hash do documento']]
    for assinatura in ordem.assinaturas.all():
        assinaturas.append([
            assinatura.get_tipo_display(),
            assinatura.usuario.get_username(),
            assinatura.assinado_em.strftime('%d/%m/%Y %H:%M'),
            assinatura.hash_documento[:16] + '…',
        ])
    tabela_assinaturas = Table(assinaturas, repeatRows=1, colWidths=[35*mm, 42*mm, 38*mm, 60*mm])
    tabela_assinaturas.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), .35, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elementos.append(tabela_assinaturas)
    doc.build(elementos)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f'{ordem.numero}.pdf')
