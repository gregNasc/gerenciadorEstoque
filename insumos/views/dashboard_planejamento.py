from datetime import timedelta
from io import BytesIO

import openpyxl
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from estoque.models import Empresa
from insumos.services.indicadores_planejamento_service import (
    IndicadoresPlanejamentoService,
)


def _id_positivo(valor):
    if not valor:
        return None
    if valor.isdigit() and int(valor) > 0:
        return int(valor)
    raise PermissionDenied('Filtro de empresa ou Base inválido.')


@login_required
def dashboard_planejamento(request):
    if not IndicadoresPlanejamentoService.pode_visualizar(request.user):
        raise PermissionDenied('Sem permissão para visualizar o planejamento.')

    perfil = request.user.perfil
    bases_acessiveis = IndicadoresPlanejamentoService.bases_permitidas(
        request.user
    ).select_related('empresa').order_by('empresa__nome', 'nome')
    empresas = Empresa.objects.filter(
        pk__in=bases_acessiveis.values('empresa_id'),
        ativa=True,
    ).order_by('nome')

    empresa_informada = 'empresa' in request.GET
    empresa_id_texto = request.GET.get('empresa', '')
    if (
        not empresa_informada
        and perfil.empresa_id
        and empresas.filter(pk=perfil.empresa_id).exists()
    ):
        empresa_id_texto = str(perfil.empresa_id)
    empresa_id = _id_positivo(empresa_id_texto)
    base_id_texto = request.GET.get('base', '')
    base_id = _id_positivo(base_id_texto)

    bases_seletor = bases_acessiveis
    if empresa_id:
        bases_seletor = bases_seletor.filter(empresa_id=empresa_id)

    hoje = timezone.localdate()
    inicio = parse_date(request.GET.get('inicio', '')) or (hoje - timedelta(days=364))
    fim = parse_date(request.GET.get('fim', '')) or hoje
    try:
        resultado = IndicadoresPlanejamentoService.gerar(
            user=request.user,
            empresa_id=empresa_id,
            base_id=base_id,
            inicio=inicio,
            fim=fim,
        )
    except ValueError as exc:
        raise PermissionDenied(str(exc)) from exc

    categorias = sorted(
        {item['categoria'] for item in resultado['itens']},
        key=str.casefold,
    )
    categoria = request.GET.get('categoria', '').strip()
    busca = request.GET.get('busca', '').strip()
    itens = resultado['itens']
    if categoria:
        itens = [item for item in itens if item['categoria'] == categoria]
    if busca:
        termo = busca.casefold()
        itens = [
            item for item in itens
            if termo in item['insumo'].casefold()
            or termo in item['categoria'].casefold()
        ]

    return render(
        request,
        'insumos/dashboard/planejamento/dashboard_planejamento.html',
        {
            'resultado': resultado,
            'itens': itens,
            'categorias': categorias,
            'empresas': empresas,
            'bases': bases_seletor,
            'filtro_empresa': empresa_id_texto,
            'filtro_base': base_id_texto,
            'filtro_categoria': categoria,
            'filtro_busca': busca,
            'inicio': inicio,
            'fim': fim,
        },
    )


@login_required
def exportar_planejamento(request):
    if not IndicadoresPlanejamentoService.pode_visualizar(request.user):
        raise PermissionDenied('Sem permissão para exportar os indicadores.')

    perfil = request.user.perfil
    empresa_id_texto = request.GET.get('empresa', '')
    if 'empresa' not in request.GET and perfil.empresa_id:
        empresa_id_texto = str(perfil.empresa_id)
    empresa_id = _id_positivo(empresa_id_texto)
    base_id = _id_positivo(request.GET.get('base', ''))
    hoje = timezone.localdate()
    inicio = parse_date(request.GET.get('inicio', '')) or (hoje - timedelta(days=364))
    fim = parse_date(request.GET.get('fim', '')) or hoje
    try:
        resultado = IndicadoresPlanejamentoService.gerar(
            user=request.user,
            empresa_id=empresa_id,
            base_id=base_id,
            inicio=inicio,
            fim=fim,
        )
    except ValueError as exc:
        raise PermissionDenied(str(exc)) from exc
    categoria = request.GET.get('categoria', '').strip()
    busca = request.GET.get('busca', '').strip().casefold()
    itens = resultado['itens']
    if categoria:
        itens = [item for item in itens if item['categoria'] == categoria]
    if busca:
        itens = [
            item for item in itens
            if busca in item['insumo'].casefold()
            or busca in item['categoria'].casefold()
        ]

    workbook = openpyxl.Workbook()
    planilha = workbook.active
    planilha.title = 'Planejamento'
    planilha.append(['PLANEJAMENTO DE CONSUMO'])
    planilha.append(['PERÍODO', inicio.strftime('%d/%m/%Y'), fim.strftime('%d/%m/%Y')])
    planilha.append([])
    planilha.append([
        'ITEM', 'CATEGORIA', 'UNIDADE', 'SOLICITADO', 'ATENDIDO',
        'CONSUMIDO', 'ESTOQUE DISPONÍVEL', 'SOLICITAÇÕES',
        'SOLICITAÇÕES ABERTAS', 'QUANTIDADE USUAL',
        'INTERVALO TÍPICO (DIAS)', 'DEMANDA ANUAL ESTIMADA',
        'FONTE DA DEMANDA', 'TENDÊNCIA', 'COBERTURA (DIAS)',
        'REFERÊNCIA 30 DIAS', 'ORIENTAÇÃO',
    ])
    for item in itens:
        planilha.append([
            item['insumo'], item['categoria'], item['unidade'],
            item['quantidade_solicitada'], item['quantidade_atendida'],
            item['quantidade_consumida'], item['estoque_disponivel'],
            item['total_solicitacoes'], item['solicitacoes_abertas'],
            item['quantidade_usual'], item['intervalo_tipico_dias'],
            item['demanda_anual_estimada'], item['fonte_demanda'],
            item['tendencia'], item['cobertura_dias'],
            item['sugestao_quantidade'], item['sugestao'],
        ])
    planilha.freeze_panes = 'A5'
    planilha.auto_filter.ref = f'A4:Q{max(planilha.max_row, 4)}'
    for celula in planilha[4]:
        celula.font = openpyxl.styles.Font(bold=True, color='FFFFFF')
        celula.fill = openpyxl.styles.PatternFill('solid', fgColor='1F3F77')
    for coluna in planilha.columns:
        largura = min(
            max(len(str(celula.value or '')) for celula in coluna) + 2,
            55,
        )
        planilha.column_dimensions[coluna[0].column_letter].width = largura

    arquivo = BytesIO()
    workbook.save(arquivo)
    response = HttpResponse(
        arquivo.getvalue(),
        content_type=(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ),
    )
    response['Content-Disposition'] = (
        f'attachment; filename="planejamento_consumo_{fim.isoformat()}.xlsx"'
    )
    return response
