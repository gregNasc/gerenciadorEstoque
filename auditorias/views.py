import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from estoque.models import Equipamento

from .forms import (
    AuditoriaBaseForm,
    CampanhaAuditoriaForm,
    RegularizacaoForm,
    RespostaDivergenciaForm,
    SolicitarCorrecaoForm,
    TransferenciaAuditoriaForm,
)
from .models import AuditoriaBase, AuditoriaDivergencia, AuditoriaLeitura, CampanhaAuditoria
from .permissions import exigir_admin, usuario_e_admin
from .selectors import auditorias_visiveis, campanhas_visiveis, divergencias_visiveis
from .services.campanha_service import CampanhaService
from .services.apuracao_service import ApuracaoService
from .services.encerramento_service import EncerramentoService
from .services.leitura_service import LeituraService
from .services.regularizacao_service import RegularizacaoService
from .services.snapshot_service import SnapshotService
from .services.relatorio_service import RelatorioService


@login_required
def campanha_lista(request):
    return render(request, 'auditorias/campanha_lista.html', {
        'campanhas': campanhas_visiveis(request.user),
        'pode_criar': usuario_e_admin(request.user),
    })


@login_required
def campanha_criar(request):
    exigir_admin(request.user)
    form = CampanhaAuditoriaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        campanha = CampanhaService.criar_campanha(criado_por=request.user, **form.cleaned_data)
        messages.success(request, 'Campanha criada.')
        return redirect('auditorias:campanha_detalhe', campanha_id=campanha.pk)
    return render(request, 'auditorias/campanha_form.html', {'form': form})


@login_required
def campanha_detalhe(request, campanha_id):
    campanha = get_object_or_404(campanhas_visiveis(request.user), pk=campanha_id)
    form_base = AuditoriaBaseForm(request.POST or None, empresa=campanha.empresa)
    if request.method == 'POST':
        exigir_admin(request.user)
        if form_base.is_valid():
            try:
                auditoria = CampanhaService.adicionar_base(
                    campanha=campanha,
                    usuario=request.user,
                    base=form_base.cleaned_data['base'],
                    inicio_em=form_base.cleaned_data['inicio_em'],
                    fim_em=form_base.cleaned_data['fim_em'],
                )
                auditoria.observacoes = form_base.cleaned_data['observacoes']
                auditoria.save(update_fields=['observacoes'])
                messages.success(request, 'Base adicionada à campanha.')
                return redirect('auditorias:campanha_detalhe', campanha_id=campanha.pk)
            except ValidationError as exc:
                form_base.add_error(None, exc)
    return render(request, 'auditorias/campanha_detalhe.html', {
        'campanha': campanha,
        'auditorias': campanha.auditorias_bases.select_related('base'),
        'form_base': form_base,
        'pode_editar': usuario_e_admin(request.user) and campanha.status == CampanhaAuditoria.Status.RASCUNHO,
        'pode_exportar_campanha': usuario_e_admin(request.user),
    })


@login_required
@require_POST
def campanha_agendar(request, campanha_id):
    campanha = get_object_or_404(campanhas_visiveis(request.user), pk=campanha_id)
    CampanhaService.agendar(campanha, request.user)
    messages.success(request, 'Campanha agendada.')
    return redirect('auditorias:campanha_detalhe', campanha_id=campanha.pk)


@login_required
@require_POST
def base_iniciar(request, auditoria_base_id):
    auditoria = get_object_or_404(auditorias_visiveis(request.user), pk=auditoria_base_id)
    try:
        SnapshotService.criar_snapshot(auditoria, request.user)
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('auditorias:coleta', auditoria_base_id=auditoria.pk)


@login_required
def coleta(request, auditoria_base_id):
    auditoria = get_object_or_404(auditorias_visiveis(request.user), pk=auditoria_base_id)
    admin = usuario_e_admin(request.user)
    pagina_equipamentos = None
    if admin:
        snapshots = auditoria.snapshot_equipamentos.select_related(
            'equipamento__produto', 'equipamento__regional', 'base_esperada'
        ).order_by('produto_descricao', 'patrimonio', 'id')
        pagina_equipamentos = Paginator(snapshots, 25).get_page(request.GET.get('pagina'))
        equipamentos_na_pagina = [item.equipamento_id for item in pagina_equipamentos]
        leituras_por_equipamento = {
            leitura.equipamento_id: leitura
            for leitura in auditoria.leituras.filter(
                equipamento_id__in=equipamentos_na_pagina,
                cancelada=False,
            ).order_by('lida_em')
        }
        status_snapshot = dict(Equipamento.STATUS_CHOICES)
        classificacoes = dict(AuditoriaLeitura.Classificacao.choices)
        for item in pagina_equipamentos:
            leitura = leituras_por_equipamento.get(item.equipamento_id)
            item.status_snapshot_display = status_snapshot.get(item.status, item.status)
            item.situacao_coleta = classificacoes.get(leitura.classificacao, leitura.classificacao) if leitura else 'Não lido'
            item.leitura_em = leitura.lida_em if leitura else None
    resultado_liberado = bool(auditoria.finalizada_em) or auditoria.status == AuditoriaBase.Status.EM_REGULARIZACAO
    return render(request, 'auditorias/coleta.html', {
        'auditoria': auditoria,
        'indicadores': EncerramentoService.indicadores(auditoria),
        'leituras': auditoria.leituras.filter(cancelada=False).order_by('-lida_em')[:25],
        'pagina_equipamentos': pagina_equipamentos,
        'pode_ver_apuracao': admin,
        'resultado_liberado': resultado_liberado,
    })


@login_required
@require_POST
def registrar_leitura(request, auditoria_base_id):
    auditoria = get_object_or_404(auditorias_visiveis(request.user), pk=auditoria_base_id)
    try:
        payload = json.loads(request.body or b'{}')
        resultado = LeituraService.registrar(
            auditoria_base=auditoria,
            valor=payload.get('valor', ''),
            usuario=request.user,
            origem=payload.get('origem', 'MANUAL'),
            idempotency_key=payload.get('idempotency_key'),
        )
        dados = resultado.to_dict()
        if not usuario_e_admin(request.user):
            duplicada = dados.get('classificacao') == AuditoriaLeitura.Classificacao.LEITURA_DUPLICADA
            dados = {
                'ok': True,
                'leitura_id': resultado.leitura.pk,
                'titulo': 'Leitura registrada',
                'mensagem': (
                    'Este identificador já foi registrado nesta auditoria.'
                    if duplicada else 'Leitura registrada para apuração do administrador.'
                ),
            }
        return JsonResponse(dados, status=201)
    except (ValueError, ValidationError) as exc:
        mensagens = exc.messages if isinstance(exc, ValidationError) else [str(exc)]
        return JsonResponse({'ok': False, 'erros': mensagens}, status=400)


@login_required
@require_POST
def base_enviar(request, auditoria_base_id):
    auditoria = get_object_or_404(auditorias_visiveis(request.user), pk=auditoria_base_id)
    destino = (
        'auditorias:divergencias'
        if usuario_e_admin(request.user)
        else 'auditorias:coleta'
    )
    if request.POST.get('confirmar_envio') != '1':
        messages.error(request, 'Confirme a conclusão antes de enviar a auditoria.')
        return redirect('auditorias:coleta', auditoria_base_id=auditoria.pk)
    try:
        resultado = EncerramentoService.enviar(auditoria, request.user)
        if resultado.status == AuditoriaBase.Status.FINALIZADA:
            messages.success(request, 'Auditoria finalizada antes do prazo, sem divergências pendentes.')
        else:
            messages.success(request, 'Auditoria enviada para análise.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect(destino, auditoria_base_id=auditoria.pk)


@login_required
def divergencias(request, auditoria_base_id):
    auditoria = get_object_or_404(auditorias_visiveis(request.user), pk=auditoria_base_id)
    admin = usuario_e_admin(request.user)
    if not admin and not (
        auditoria.finalizada_em or auditoria.status == AuditoriaBase.Status.EM_REGULARIZACAO
    ):
        raise PermissionDenied('O resultado ainda está em apuração pelo administrador.')
    divergencias = divergencias_visiveis(request.user).filter(auditoria_base=auditoria)
    return render(request, 'auditorias/divergencias.html', {
        'auditoria': auditoria,
        'divergencias': divergencias,
        'admin': admin,
        'pode_reabrir': admin and auditoria.status in (
            AuditoriaBase.Status.ENVIADA,
            AuditoriaBase.Status.COM_DIVERGENCIAS,
            AuditoriaBase.Status.EM_REGULARIZACAO,
            AuditoriaBase.Status.FINALIZADA,
        ),
        'pode_validar': admin and not auditoria.finalizada_em and auditoria.status in (
            AuditoriaBase.Status.ENVIADA,
            AuditoriaBase.Status.COM_DIVERGENCIAS,
            AuditoriaBase.Status.EM_REGULARIZACAO,
        ),
        'pode_solicitar_correcao': admin and not auditoria.finalizada_em and auditoria.status in (
            AuditoriaBase.Status.ENVIADA,
            AuditoriaBase.Status.COM_DIVERGENCIAS,
            AuditoriaBase.Status.EM_REGULARIZACAO,
        ),
        'form_correcao': SolicitarCorrecaoForm(),
        'prazo_correcao_ativo': bool(
            auditoria.prazo_correcao_em and timezone.now() <= auditoria.prazo_correcao_em
        ),
        'resultado_finalizado': bool(auditoria.finalizada_em),
        'pode_baixar_relatorio': admin or bool(auditoria.finalizada_em),
    })


@login_required
@require_POST
def base_reabrir(request, auditoria_base_id):
    auditoria = get_object_or_404(auditorias_visiveis(request.user), pk=auditoria_base_id)
    exigir_admin(request.user)
    try:
        CampanhaService.reabrir_base(
            auditoria,
            request.user,
            request.POST.get('justificativa', ''),
        )
        messages.success(request, 'Auditoria reaberta. As leituras anteriores foram preservadas.')
        return redirect('auditorias:coleta', auditoria_base_id=auditoria.pk)
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
        return redirect('auditorias:divergencias', auditoria_base_id=auditoria.pk)


@login_required
@require_POST
def base_finalizar(request, auditoria_base_id):
    auditoria = get_object_or_404(auditorias_visiveis(request.user), pk=auditoria_base_id)
    exigir_admin(request.user)
    if request.POST.get('confirmar_validacao') != '1':
        messages.error(request, 'Confirme a validação do resultado antes de continuar.')
        return redirect('auditorias:divergencias', auditoria_base_id=auditoria.pk)
    try:
        ApuracaoService.validar_resultado(auditoria, request.user)
        messages.success(
            request,
            'Resultado validado como fonte de verdade e relatório final liberado para a base.',
        )
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('auditorias:divergencias', auditoria_base_id=auditoria.pk)


@login_required
@require_POST
def base_solicitar_correcao(request, auditoria_base_id):
    auditoria = get_object_or_404(auditorias_visiveis(request.user), pk=auditoria_base_id)
    exigir_admin(request.user)
    form = SolicitarCorrecaoForm(request.POST)
    if form.is_valid():
        try:
            ApuracaoService.solicitar_correcao(
                auditoria,
                request.user,
                prazo_correcao_em=form.cleaned_data['prazo_correcao_em'],
                orientacoes=form.cleaned_data['orientacoes_correcao'],
            )
            messages.success(request, 'Correções solicitadas e prazo comunicado à base.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
    else:
        messages.error(request, 'Revise o prazo e as orientações da solicitação de correção.')
    return redirect('auditorias:divergencias', auditoria_base_id=auditoria.pk)


@login_required
def divergencia_detalhe(request, divergencia_id):
    divergencia = get_object_or_404(divergencias_visiveis(request.user), pk=divergencia_id)
    em_correcao = divergencia.auditoria_base.status == AuditoriaBase.Status.EM_REGULARIZACAO
    prazo_ativo = bool(
        divergencia.auditoria_base.prazo_correcao_em
        and timezone.now() <= divergencia.auditoria_base.prazo_correcao_em
    )
    if not usuario_e_admin(request.user) and not (
        divergencia.auditoria_base.finalizada_em or em_correcao
    ):
        raise PermissionDenied('O resultado ainda está em apuração pelo administrador.')
    return render(request, 'auditorias/divergencia_detalhe.html', {
        'divergencia': divergencia,
        'pode_regularizar': em_correcao and prazo_ativo,
        'pode_responder': em_correcao and prazo_ativo and not usuario_e_admin(request.user),
        'em_correcao': em_correcao,
        'prazo_ativo': prazo_ativo,
        'admin': usuario_e_admin(request.user),
        'pode_inativar': bool(
            usuario_e_admin(request.user)
            and divergencia.tipo == AuditoriaDivergencia.Tipo.NAO_LOCALIZADO
            and divergencia.equipamento_id
            and divergencia.status in (
                AuditoriaDivergencia.Status.ABERTA,
                AuditoriaDivergencia.Status.EM_ANALISE,
            )
            and not hasattr(divergencia, 'resolucao')
        ),
        'form_resposta': RespostaDivergenciaForm(
            initial={'justificativa_base': divergencia.justificativa_base}
        ),
        'form_manter': RegularizacaoForm(),
        'form_transferir': TransferenciaAuditoriaForm(
            empresa=divergencia.auditoria_base.campanha.empresa,
            excluir_base=divergencia.base_encontrada,
        ),
    })


@login_required
@require_POST
def divergencia_inativar(request, divergencia_id):
    divergencia = get_object_or_404(divergencias_visiveis(request.user), pk=divergencia_id)
    exigir_admin(request.user)
    try:
        ApuracaoService.inativar_nao_localizado(
            divergencia,
            request.user,
            request.POST.get('justificativa', ''),
        )
        messages.success(request, 'Equipamento inativado e divergência resolvida com rastreabilidade.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('auditorias:divergencia_detalhe', divergencia_id=divergencia.pk)


@login_required
@require_POST
def divergencia_responder(request, divergencia_id):
    divergencia = get_object_or_404(divergencias_visiveis(request.user), pk=divergencia_id)
    form = RespostaDivergenciaForm(request.POST)
    if form.is_valid():
        try:
            ApuracaoService.responder_divergencia(
                divergencia,
                request.user,
                form.cleaned_data['justificativa_base'],
            )
            messages.success(request, 'Justificativa enviada para análise do administrador.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
    return redirect('auditorias:divergencia_detalhe', divergencia_id=divergencia.pk)


@login_required
@require_POST
def divergencia_manter(request, divergencia_id):
    divergencia = get_object_or_404(divergencias_visiveis(request.user), pk=divergencia_id)
    form = RegularizacaoForm(request.POST)
    if form.is_valid():
        try:
            RegularizacaoService.manter_na_base(
                divergencia=divergencia,
                usuario=request.user,
                justificativa=form.cleaned_data['justificativa'],
            )
            messages.success(request, 'Equipamento mantido na base encontrada.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
    return redirect('auditorias:divergencia_detalhe', divergencia_id=divergencia.pk)


@login_required
@require_POST
def divergencia_transferir(request, divergencia_id):
    divergencia = get_object_or_404(divergencias_visiveis(request.user), pk=divergencia_id)
    form = TransferenciaAuditoriaForm(
        request.POST,
        empresa=divergencia.auditoria_base.campanha.empresa,
        excluir_base=divergencia.base_encontrada,
    )
    if form.is_valid():
        try:
            transferencia = RegularizacaoService.transferir(
                divergencia=divergencia,
                base_destino=form.cleaned_data['base_destino'],
                usuario=request.user,
                justificativa=form.cleaned_data['justificativa'],
            )
            messages.success(request, f'Transferência {transferencia.protocolo} criada.')
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
    return redirect('auditorias:divergencia_detalhe', divergencia_id=divergencia.pk)


@login_required
def relatorio_base(request, auditoria_base_id, formato):
    if formato != 'xlsx':
        raise Http404
    auditoria = get_object_or_404(auditorias_visiveis(request.user), pk=auditoria_base_id)
    if not usuario_e_admin(request.user) and not auditoria.finalizada_em:
        raise PermissionDenied('O relatório final ainda não foi liberado pelo administrador.')
    titulo, linhas = RelatorioService.dados_base(auditoria)
    conteudo, content_type = RelatorioService.exportar(titulo, linhas, formato)
    resposta = HttpResponse(conteudo, content_type=content_type)
    tipo = 'final' if auditoria.finalizada_em else 'parcial'
    resposta['Content-Disposition'] = f'attachment; filename="auditoria-base-{auditoria.pk}-{tipo}.{formato}"'
    return resposta


@login_required
def relatorio_campanha(request, campanha_id, formato):
    if formato != 'xlsx':
        raise Http404
    campanha = get_object_or_404(campanhas_visiveis(request.user), pk=campanha_id)
    exigir_admin(request.user)
    titulo, linhas = RelatorioService.dados_campanha(campanha)
    conteudo, content_type = RelatorioService.exportar(titulo, linhas, formato)
    resposta = HttpResponse(conteudo, content_type=content_type)
    resposta['Content-Disposition'] = f'attachment; filename="auditoria-campanha-{campanha.pk}.{formato}"'
    return resposta
