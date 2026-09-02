from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from estoque.models import Equipamento, Produto
from estoque.security import secure_queryset
from estoque.services.documentation_service import DocumentationService
from chamados.forms import (
    ChamadoAvaliacaoForm,
    ChamadoForm,
    ChamadoMensagemForm,
    ChamadoSickForm,
    ChamadoStatusForm,
    ChamadoTransferenciaForm,
)
from chamados.equipment_images import equipment_image_for
from datetime import datetime, time, timedelta
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
        'pode_criar': bool(
            ChamadoAccessPolicy.bases(request.user).exists()
            and not ChamadoAccessPolicy.e_admin(request.user)
        ),
        'pode_dashboard': ChamadoAccessPolicy.pode_dashboard(request.user),
        'pode_exportar': bool(
            ChamadoAccessPolicy.e_admin(request.user)
            or request.user.has_perm('chamados.exportar_chamados')
            or ChamadoAccessPolicy.pode_dashboard(request.user)
        ),
    })

@login_required
def equipamentos_por_categoria(request):
    categoria = (
        request.GET.get('categoria')
        or ''
    ).strip()

    base_id = (
        request.GET.get('base')
        or ''
    ).strip()

    # Categoria obrigatória
    if not categoria:
        return JsonResponse({
            'equipamentos': [],
        })

    if categoria == 'Sistema':
        return JsonResponse({
            'equipamentos': [],
            'equipamento_opcional': True,
        })

    # Validar categoria
    categorias_validas = {
        valor
        for valor, _rotulo
        in Produto.CATEGORIAS
    }

    if categoria not in categorias_validas:
        return JsonResponse(
            {
                'erro': 'Categoria inválida.',
                'equipamentos': [],
            },
            status=400,
        )

    # Bases que o usuário realmente pode acessar
    bases_permitidas = (
        ChamadoAccessPolicy.bases(
            request.user
        )
    )

    base = None

    # Usuário normal: sua única base é usada
    # independentemente do parâmetro recebido.
    if bases_permitidas.count() == 1:
        base = bases_permitidas.first()

    # Admin / usuário com várias bases
    elif base_id.isdigit():
        base = bases_permitidas.filter(
            pk=base_id
        ).first()

    if not base:
        return JsonResponse(
            {
                'erro': 'Base inválida ou não autorizada.',
                'equipamentos': [],
            },
            status=400,
        )

    # Equipamentos:
    # - da base
    # - da categoria
    equipamentos = (
        Equipamento.objects
        .filter(
            regional=base,
            produto__categoria=categoria,
        )
        .select_related(
            'produto',
            'regional',
        )
    )

    # Mantém as mesmas regras de segurança
    # usadas pelo estoque.
    equipamentos = secure_queryset(
        equipamentos,
        request.user,
    )

    equipamentos = equipamentos.order_by(
        'produto__descricao',
        'patrimonio',
    )

    resultado = []

    for equipamento in equipamentos:
        produto = equipamento.produto

        partes = []

        if equipamento.patrimonio:
            partes.append(
                f'Patrimônio: {equipamento.patrimonio}'
            )

        if produto:
            partes.append(
                produto.descricao
            )

        if equipamento.numero_serie:
            partes.append(
                f'S/N: {equipamento.numero_serie}'
            )

        resultado.append({
            'id': equipamento.pk,
            'texto': ' · '.join(partes),
        })

    return JsonResponse({
        'equipamentos': resultado,
    })

@login_required
def criar(request):
    if ChamadoAccessPolicy.e_admin(request.user):
        raise PermissionDenied('ADMINISTRADORES ATENDEM CHAMADOS E NÃO ABREM SOLICITAÇÕES.')
    form = ChamadoForm(
        request.POST or None,
        user=request.user,
    )

    if request.method == 'POST' and form.is_valid():
        try:
            chamado = ChamadoService.abrir(
                usuario=request.user,
                **form.cleaned_data,
            )
        except (PermissionDenied, ValidationError) as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                f'CHAMADO {chamado.protocolo} ABERTO COM SUCESSO.'
            )
            return redirect(
                'chamados:detalhe',
                pk=chamado.pk,
            )

    inventarios_contexto = {
        str(inventario.pk): {
            'lider': inventario.lider or '',
            'loja': inventario.loja or '',
        }
        for inventario
        in form.fields['inventario'].queryset
    }

    return render(
        request,
        'chamados/form.html',
        {
            'form': form,
            'hoje': timezone.localdate(),
            'inventarios_contexto': inventarios_contexto,
            'atendentes_online': ChamadoAccessPolicy.atendentes_online_para(),
        }
    )

@login_required
def detalhe(request, pk):
    chamado = get_object_or_404(
        ChamadoAccessPolicy.queryset(request.user).select_related(
            'empresa', 'base', 'categoria', 'inventario__cliente', 'equipamento__produto',
            'sick', 'aberto_por', 'atendente',
        ).prefetch_related(
            'mensagens__autor', 'mensagens__anexos', 'eventos__usuario',
            'sessoes', 'transferencias_atendente',
        ),
        pk=pk,
    )
    pode_atender = ChamadoAccessPolicy.pode_atender(request.user)
    mensagens_qs = chamado.mensagens.all()
    if not pode_atender:
        mensagens_qs = mensagens_qs.filter(nota_interna=False)
    status_permitidos = ChamadoService.status_permitidos(chamado, request.user)
    ordens = OrdemServico.objects.filter(chamado_referencia=chamado.protocolo).order_by('-aberto_em')
    documentacao_contextual = (
        DocumentationService.para_produto(chamado.equipamento.produto)
        if chamado.equipamento_id and chamado.equipamento.produto_id
        else []
    )
    equipamento_imagem = (
        equipment_image_for(chamado.equipamento.produto)
        if chamado.equipamento_id and chamado.equipamento.produto_id
        else None
    )
    return render(request, 'chamados/detalhe.html', {
        'chamado': chamado,
        'mensagens_chamado': mensagens_qs,
        'avaliacoes_chamado': chamado.avaliacoes.select_related(
            'atendimento__atendente', 'solicitante',
        ).order_by('-criada_em'),
        'mensagem_form': ChamadoMensagemForm(),
        'status_form': ChamadoStatusForm(
            status_permitidos=status_permitidos,
            initial={'resolucao': chamado.resolucao, 'causa_raiz': chamado.causa_raiz},
        ),
        'avaliacao_form': ChamadoAvaliacaoForm(),
        'transferencia_form': ChamadoTransferenciaForm(chamado=chamado),
        'sick_form': ChamadoSickForm(),
        'status_permitidos': status_permitidos,
        'pode_atender': pode_atender,
        # Evaluations are management data. They are deliberately unavailable
        # to both the requester and the attendant after submission.
        'pode_ver_avaliacoes': ChamadoAccessPolicy.e_admin(request.user),
        'pode_interagir': ChamadoAccessPolicy.pode_interagir(request.user, chamado),
        'pode_avaliar': chamado.aberto_por_id == request.user.pk and chamado.status == Chamado.Status.AVALIACAO,
        'pode_transferir': chamado.atendente_id and ChamadoAccessPolicy.pode_transferir(request.user, chamado),
        'pode_converter_sick': not chamado.sick_id and ChamadoAccessPolicy.pode_converter_sick(request.user, chamado),
        'metricas': ChamadoService.metricas(chamado),
        'ordens': ordens,
        'documentacao_contextual': documentacao_contextual,
        'equipamento_imagem': equipamento_imagem,
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
                chamado,
                request.user,
                form.cleaned_data['status'],
                form.cleaned_data['resolucao'],
                form.cleaned_data['causa_raiz'],
            )
            messages.success(request, 'STATUS ATUALIZADO.')
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'VERIFIQUE O STATUS E A RESOLUÇÃO INFORMADOS.')
    return redirect('chamados:detalhe', pk=pk)

@login_required
@require_POST
def avaliar(request, pk):
    chamado = get_object_or_404(ChamadoAccessPolicy.queryset(request.user), pk=pk)
    form = ChamadoAvaliacaoForm(request.POST)
    if form.is_valid():
        try:
            avaliacao = ChamadoService.avaliar(chamado, request.user, **form.cleaned_data)
            messages.success(request, 'AVALIAÇÃO REGISTRADA.')
        except (PermissionDenied, ValidationError) as exc:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'ok': False, 'erro': str(exc)}, status=400)
            messages.error(request, str(exc))
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                chamado.refresh_from_db(fields=['status'])
                return JsonResponse({
                    'ok': True,
                    'avaliacao_id': avaliacao.pk,
                    'status': chamado.get_status_display(),
                    'encerrado': chamado.status == Chamado.Status.ENCERRADO,
                })
    else:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'erros': form.errors.get_json_data()}, status=400)
        messages.error(request, 'VERIFIQUE A NOTA E A CONFIRMAÇÃO DA SOLUÇÃO.')
    return redirect('chamados:detalhe', pk=pk)

@login_required
@require_POST
def transferir(request, pk):
    chamado = get_object_or_404(ChamadoAccessPolicy.queryset(request.user), pk=pk)
    form = ChamadoTransferenciaForm(request.POST, chamado=chamado)
    if form.is_valid():
        try:
            ChamadoService.transferir_atendente(chamado, request.user, **form.cleaned_data)
            messages.success(request, 'ATENDIMENTO TRANSFERIDO.')
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'VERIFIQUE O NOVO ATENDENTE E O MOTIVO.')
    return redirect('chamados:detalhe', pk=pk)

@login_required
@require_POST
def converter_sick(request, pk):
    chamado = get_object_or_404(ChamadoAccessPolicy.queryset(request.user), pk=pk)
    form = ChamadoSickForm(request.POST)
    if form.is_valid():
        try:
            ChamadoService.converter_em_sick(chamado, request.user, **form.cleaned_data)
            messages.success(request, 'SICK CRIADO COM O.S. E RASTREABILIDADE.')
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, 'INFORME O DIAGNÓSTICO PARA O SICK.')
    return redirect('chamados:detalhe', pk=pk)

@login_required
def baixar_anexo(request, pk):
    anexo = get_object_or_404(ChamadoAnexo.objects.select_related('chamado'), pk=pk)
    if not ChamadoAccessPolicy.pode_ver(request.user, anexo.chamado):
        raise PermissionDenied
    if anexo.mensagem and anexo.mensagem.nota_interna and not ChamadoAccessPolicy.pode_atender(request.user):
        raise PermissionDenied
    resposta = FileResponse(
        anexo.arquivo.open('rb'),
        as_attachment=True,
        filename=anexo.nome_original,
        content_type='application/octet-stream',
    )
    resposta['X-Content-Type-Options'] = 'nosniff'
    resposta['Content-Security-Policy'] = "sandbox; default-src 'none'"
    return resposta

def _media_duracoes(duracoes):
    segundos = [
        duracao.total_seconds()
        for duracao in duracoes
        if duracao is not None
    ]

    if not segundos:
        return None

    return sum(segundos) / len(segundos)

def _formatar_tempo(segundos):
    if segundos is None:
        return '—'

    segundos = int(segundos)

    dias, resto = divmod(
        segundos,
        86400,
    )

    horas, resto = divmod(
        resto,
        3600,
    )

    minutos, segundos = divmod(
        resto,
        60,
    )

    if dias:
        return (
            f'{dias}d '
            f'{horas}h '
            f'{minutos}min'
        )

    if horas:
        return (
            f'{horas}h '
            f'{minutos:02d}min'
        )

    if minutos:
        return (
            f'{minutos}min '
            f'{segundos:02d}s'
        )

    return f'{segundos}s'

@login_required
def dashboard(request):
    if not ChamadoAccessPolicy.pode_dashboard(
        request.user
    ):
        raise PermissionDenied

    # ESCOPO DE ACESSO

    qs = ChamadoAccessPolicy.queryset(
        request.user
    )

    agora = timezone.now()
    hoje = timezone.localdate()

    # PERÍODO

    periodo = (
        request.GET.get('periodo')
        or 'hoje'
    ).strip()

    if periodo == '7d':
        data_inicio = (
            hoje - timedelta(days=6)
        )
        periodo_label = 'Últimos 7 dias'

    elif periodo == '30d':
        data_inicio = (
            hoje - timedelta(days=29)
        )
        periodo_label = 'Últimos 30 dias'

    else:
        periodo = 'hoje'
        data_inicio = hoje
        periodo_label = 'Hoje'

    inicio_periodo = timezone.make_aware(
        datetime.combine(
            data_inicio,
            time.min,
        ),
        timezone.get_current_timezone(),
    )

    # STATUS TERMINAIS

    terminais = {
        Chamado.Status.RESOLVIDO,
        Chamado.Status.AVALIACAO,
        Chamado.Status.ENCERRADO,
        Chamado.Status.CANCELADO,
    }

    # BACKLOG ATUAL
    #
    # Não depende do período.

    backlog = qs.exclude(
        status__in=terminais
    )

    aguardando = backlog.filter(
        status__in={
            Chamado.Status.ABERTO,
            Chamado.Status.AGUARDANDO_ATENDIMENTO,
            Chamado.Status.REABERTO,
        }
    ).count()

    em_atendimento = backlog.filter(
        status=Chamado.Status.EM_ATENDIMENTO
    ).count()

    aguardando_solicitante = backlog.filter(
        status=Chamado.Status.AGUARDANDO_SOLICITANTE
    ).count()

    sla_vencido = backlog.filter(
        prazo_sla_em__lt=agora
    ).count()

    criticos = backlog.filter(
        prioridade=Chamado.Prioridade.CRITICA
    ).count()

    # CHAMADOS ABERTOS NO PERÍODO

    chamados_periodo = qs.filter(
        aberto_em__gte=inicio_periodo,
        aberto_em__lte=agora,
    )

    # RESOLVIDOS NO PERÍODO
    #
    # Aqui usamos a data de resolução, não a abertura.

    resolvidos_periodo_qs = qs.filter(
        resolvido_em__isnull=False,
        resolvido_em__gte=inicio_periodo,
        resolvido_em__lte=agora,
    )

    resolvidos_periodo = (
        resolvidos_periodo_qs.count()
    )

    # PRIMEIRA RESPOSTA

    tempos_primeira_resposta = []

    for (
        aberto_em,
        primeira_resposta_em,
    ) in chamados_periodo.exclude(
        primeira_resposta_em__isnull=True
    ).values_list(
        'aberto_em',
        'primeira_resposta_em',
    ):

        tempos_primeira_resposta.append(
            primeira_resposta_em
            - aberto_em
        )

    media_primeira_resposta = (
        _media_duracoes(
            tempos_primeira_resposta
        )
    )

    # TEMPO ATÉ ACEITE

    tempos_aceite = []

    for (
        aberto_em,
        aceito_em,
    ) in chamados_periodo.exclude(
        aceito_em__isnull=True
    ).values_list(
        'aberto_em',
        'aceito_em',
    ):

        tempos_aceite.append(
            aceito_em - aberto_em
        )

    media_aceite = _media_duracoes(
        tempos_aceite
    )

    # TEMPO DE RESOLUÇÃO

    tempos_resolucao = []

    for (
        aberto_em,
        resolvido_em,
    ) in resolvidos_periodo_qs.values_list(
        'aberto_em',
        'resolvido_em',
    ):

        tempos_resolucao.append(
            resolvido_em - aberto_em
        )

    media_resolucao = (
        _media_duracoes(
            tempos_resolucao
        )
    )

    # TIPOS DE SUPORTE MAIS FREQUENTES

    tipos_suporte_brutos = list(
        chamados_periodo
        .values(
            'categoria__nome',
            'categoria_equipamento',
        )
        .annotate(
            total=Count('id')
        )
    )

    tipos_suporte_acumulados = {}

    for item in tipos_suporte_brutos:
        tipo = (
            item['categoria__nome']
            or item['categoria_equipamento']
            or 'Não informado'
        )
        tipos_suporte_acumulados[tipo] = (
            tipos_suporte_acumulados.get(tipo, 0)
            + item['total']
        )

    por_categoria = [
        {
            'tipo_suporte': tipo,
            'total': total,
        }
        for tipo, total in sorted(
            tipos_suporte_acumulados.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    # BASE

    por_base = list(
        chamados_periodo
        .values(
            'base__nome'
        )
        .annotate(
            total=Count('id')
        )
        .order_by('-total')[:10]
    )

    # IDADE DO BACKLOG

    uma_hora = (
        agora - timedelta(hours=1)
    )

    quatro_horas = (
        agora - timedelta(hours=4)
    )

    oito_horas = (
        agora - timedelta(hours=8)
    )

    vinte_quatro_horas = (
        agora - timedelta(hours=24)
    )

    por_idade = [
        {
            'faixa': '< 1h',
            'total': backlog.filter(
                aberto_em__gte=uma_hora
            ).count(),
        },
        {
            'faixa': '1–4h',
            'total': backlog.filter(
                aberto_em__lt=uma_hora,
                aberto_em__gte=quatro_horas,
            ).count(),
        },
        {
            'faixa': '4–8h',
            'total': backlog.filter(
                aberto_em__lt=quatro_horas,
                aberto_em__gte=oito_horas,
            ).count(),
        },
        {
            'faixa': '8–24h',
            'total': backlog.filter(
                aberto_em__lt=oito_horas,
                aberto_em__gte=vinte_quatro_horas,
            ).count(),
        },
        {
            'faixa': '> 24h',
            'total': backlog.filter(
                aberto_em__lt=vinte_quatro_horas
            ).count(),
        },
    ]

    # CHAMADOS QUE EXIGEM ATENÇÃO

    chamados_atencao = (
        backlog
        .filter(
            Q(
                prioridade=Chamado.Prioridade.CRITICA
            )
            |
            Q(
                prazo_sla_em__lt=agora
            )
        )
        .select_related(
            'base',
            'equipamento__produto',
            'atendente',
        )
        .order_by(
            'prazo_sla_em',
            'aberto_em',
        )[:8]
    )

    # RENDER

    return render(
        request,
        'chamados/dashboard.html',
        {
            # Período
            'periodo': periodo,
            'periodo_label': periodo_label,

            # Situação atual
            'aguardando': aguardando,
            'em_atendimento': em_atendimento,
            'aguardando_solicitante': aguardando_solicitante,
            'sla_vencido': sla_vencido,
            'criticos': criticos,

            # Desempenho
            'media_primeira_resposta':
                _formatar_tempo(
                    media_primeira_resposta
                ),

            'media_aceite':
                _formatar_tempo(
                    media_aceite
                ),

            'media_resolucao':
                _formatar_tempo(
                    media_resolucao
                ),

            'resolvidos_periodo':
                resolvidos_periodo,

            # Gráficos
            'por_categoria': por_categoria,
            'por_base': por_base,
            'por_idade': por_idade,

            # Atenção
            'chamados_atencao':
                chamados_atencao,
        },
    )

@login_required
def exportar(request):
    # openpyxl é pesado e esta view não participa do fluxo normal nem do chat.
    # O import local evita carregá-lo no startup de todos os processos ASGI.
    from io import BytesIO

    from openpyxl import Workbook

    if not (
        ChamadoAccessPolicy.e_admin(request.user)
        or request.user.has_perm('chamados.exportar_chamados')
        or ChamadoAccessPolicy.pode_dashboard(request.user)
    ):
        raise PermissionDenied
    qs = _filtrar(
        request,
        ChamadoAccessPolicy.queryset(request.user).select_related(
            'base', 'categoria', 'aberto_por', 'atendente', 'inventario__cliente'
        ),
    )
    workbook = Workbook()
    planilha = workbook.active
    planilha.title = 'CHAMADOS'
    planilha.append([
        'PROTOCOLO', 'BASE', 'SIGLA DA LOJA', 'NÚMERO DA LOJA', 'CATEGORIA',
        'TÍTULO', 'PRIORIDADE', 'STATUS', 'ABERTO POR', 'ATENDENTE', 'ABERTURA',
        'RESOLUÇÃO',
    ])
    for chamado in qs.iterator():
        planilha.append([_excel_seguro(valor) for valor in [
            chamado.protocolo,
            chamado.base.nome,
            chamado.inventario.cliente.sigla if chamado.inventario_id else '',
            chamado.loja,
            chamado.categoria_equipamento,
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
