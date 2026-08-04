from io import BytesIO

from openpyxl import Workbook
from django.utils import timezone

from estoque.models import Equipamento

from auditorias.models import AuditoriaDivergencia, AuditoriaLeitura

from .encerramento_service import EncerramentoService


class RelatorioService:
    @staticmethod
    def _data_hora(valor):
        return timezone.localtime(valor).strftime('%d/%m/%Y %H:%M') if valor else ''

    @classmethod
    def linhas_equipamentos(cls, auditoria, incluir_base=False):
        leituras = {
            leitura.equipamento_id: leitura
            for leitura in auditoria.leituras.filter(
                cancelada=False,
                equipamento__isnull=False,
            ).select_related('equipamento').order_by('lida_em')
        }
        divergencias = {}
        for divergencia in auditoria.divergencias.select_related('equipamento').order_by('criada_em'):
            if divergencia.equipamento_id:
                divergencias.setdefault(divergencia.equipamento_id, []).append(divergencia)
        status_equipamento = {valor: str(rotulo) for valor, rotulo in Equipamento.STATUS_CHOICES}
        classificacoes = {valor: str(rotulo) for valor, rotulo in AuditoriaLeitura.Classificacao.choices}
        cabecalho = []
        if incluir_base:
            cabecalho.append('Base auditada')
        cabecalho.extend([
            'Código', 'Patrimônio', 'Número de série', 'Produto', 'Categoria',
            'Base esperada', 'Base atual', 'Status no snapshot', 'Status atual',
            'Situação da coleta', 'Data da leitura', 'Divergências', 'Ação necessária',
        ])
        linhas = [cabecalho]
        snapshots = auditoria.snapshot_equipamentos.select_related(
            'equipamento__regional', 'base_esperada'
        ).order_by('produto_descricao', 'patrimonio', 'id')
        for snapshot in snapshots:
            leitura = leituras.get(snapshot.equipamento_id)
            divergencias_item = divergencias.get(snapshot.equipamento_id, [])
            abertas = [
                item for item in divergencias_item
                if item.status not in (
                    AuditoriaDivergencia.Status.RESOLVIDA,
                    AuditoriaDivergencia.Status.CANCELADA,
                )
            ]
            if any(item.status == AuditoriaDivergencia.Status.AGUARDANDO_TRANSFERENCIA for item in abertas):
                acao_necessaria = 'Em andamento — transferência pendente'
            elif abertas:
                acao_necessaria = 'Sim — correção necessária'
            elif divergencias_item:
                acao_necessaria = 'Não — divergência resolvida'
            else:
                acao_necessaria = 'Não'
            linha = []
            if incluir_base:
                linha.append(auditoria.base.nome)
            linha.extend([
                snapshot.codigo,
                snapshot.patrimonio,
                snapshot.numero_serie,
                snapshot.produto_descricao,
                snapshot.categoria,
                snapshot.base_esperada.nome,
                snapshot.equipamento.regional.nome,
                status_equipamento.get(snapshot.status, snapshot.status),
                snapshot.equipamento.get_status_display(),
                classificacoes.get(leitura.classificacao, leitura.classificacao) if leitura else 'Não lido',
                cls._data_hora(leitura.lida_em) if leitura else '',
                '; '.join(
                    f'{item.get_tipo_display()} ({item.get_status_display()})'
                    for item in divergencias_item
                ),
                acao_necessaria,
            ])
            linhas.append(linha)
        return linhas

    @classmethod
    def linhas_divergencias(cls, auditoria, incluir_base=False):
        cabecalho = []
        if incluir_base:
            cabecalho.append('Base auditada')
        cabecalho.extend([
            'Tipo', 'Situação', 'Identificador informado', 'Tipo do identificador',
            'Código', 'Patrimônio', 'Número de série',
            'Produto', 'Status atual', 'Base esperada', 'Base encontrada', 'Descrição',
            'Justificativa da base', 'Respondida em', 'Ação necessária',
        ])
        linhas = [cabecalho]
        for divergencia in auditoria.divergencias.select_related(
            'equipamento__produto', 'leitura', 'base_esperada', 'base_encontrada'
        ).order_by('tipo', 'criada_em'):
            equipamento = divergencia.equipamento
            if divergencia.status == AuditoriaDivergencia.Status.AGUARDANDO_TRANSFERENCIA:
                acao_necessaria = 'Em andamento — transferência pendente'
            elif divergencia.status in (
                AuditoriaDivergencia.Status.RESOLVIDA,
                AuditoriaDivergencia.Status.CANCELADA,
            ):
                acao_necessaria = 'Não'
            else:
                acao_necessaria = 'Sim — correção necessária'
            linha = []
            if incluir_base:
                linha.append(auditoria.base.nome)
            linha.extend([
                divergencia.get_tipo_display(),
                divergencia.get_status_display(),
                divergencia.identificador_informado,
                divergencia.tipo_identificador_informado,
                equipamento.codigo if equipamento else '',
                equipamento.patrimonio if equipamento else '',
                equipamento.numero_serie if equipamento else '',
                equipamento.produto.descricao if equipamento and equipamento.produto else '',
                equipamento.get_status_display() if equipamento else '',
                divergencia.base_esperada.nome if divergencia.base_esperada else '',
                divergencia.base_encontrada.nome if divergencia.base_encontrada else '',
                divergencia.descricao,
                divergencia.justificativa_base,
                cls._data_hora(divergencia.respondida_em),
                acao_necessaria,
            ])
            linhas.append(linha)
        return linhas

    @staticmethod
    def dados_base(auditoria):
        indicadores = EncerramentoService.indicadores(auditoria)
        linhas = [
            ['Indicador', 'Valor'],
            ['Tipo do relatório', 'Final' if auditoria.finalizada_em else 'Parcial'],
            ['Base', auditoria.base.nome],
            ['Campanha', auditoria.campanha.nome],
            ['Status', auditoria.get_status_display()],
            ['Esperados', indicadores['esperados']],
            ['Lidos', indicadores['lidos']],
            ['Corretos', indicadores['corretos']],
            ['Divergências abertas', indicadores['divergencias_abertas']],
            ['Conformidade (%)', indicadores['conformidade'] if indicadores['conformidade'] is not None else 'N/A'],
        ]
        if auditoria.correcao_solicitada_em:
            linhas.extend([
                ['Prazo para correção', RelatorioService._data_hora(auditoria.prazo_correcao_em)],
                ['Orientações para correção', auditoria.orientacoes_correcao],
            ])
        linhas.extend([[], ['Equipamentos auditados']])
        linhas.extend(RelatorioService.linhas_equipamentos(auditoria))
        linhas.extend([[], ['Divergências detalhadas']])
        linhas.extend(RelatorioService.linhas_divergencias(auditoria))
        return f'Auditoria - {auditoria.base.nome}', linhas

    @staticmethod
    def dados_campanha(campanha):
        linhas = [['Base', 'Status', 'Esperados', 'Lidos', 'Corretos', 'Divergências', 'Conformidade (%)']]
        for auditoria in campanha.auditorias_bases.select_related('base'):
            indicadores = EncerramentoService.indicadores(auditoria)
            linhas.append([
                auditoria.base.nome,
                auditoria.get_status_display(),
                indicadores['esperados'],
                indicadores['lidos'],
                indicadores['corretos'],
                indicadores['divergencias_abertas'],
                indicadores['conformidade'] if indicadores['conformidade'] is not None else 'N/A',
            ])
        linhas.extend([[], ['Equipamentos auditados']])
        for auditoria in campanha.auditorias_bases.select_related('base'):
            bloco = RelatorioService.linhas_equipamentos(auditoria, incluir_base=True)
            if len(linhas) and linhas[-1] and linhas[-1][0] == 'Equipamentos auditados':
                linhas.extend(bloco)
            else:
                linhas.extend(bloco[1:])
        linhas.extend([[], ['Divergências detalhadas']])
        primeira = True
        for auditoria in campanha.auditorias_bases.select_related('base'):
            bloco = RelatorioService.linhas_divergencias(auditoria, incluir_base=True)
            linhas.extend(bloco if primeira else bloco[1:])
            primeira = False
        return f'Campanha - {campanha.nome}', linhas

    @classmethod
    def exportar(cls, titulo, linhas, formato):
        if formato != 'xlsx':
            raise ValueError('Somente o formato XLSX está disponível para relatórios de auditoria.')
        total_colunas = max(len(linha) for linha in linhas)
        linhas = [list(linha) + [''] * (total_colunas - len(linha)) for linha in linhas]
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Relatório'
        for linha in linhas:
            sheet.append(linha)
        sheet.freeze_panes = 'A2'
        for cell in sheet[1]:
            cell.font = cell.font.copy(bold=True)
        for coluna in sheet.columns:
            largura = min(max(len(str(cell.value or '')) for cell in coluna) + 2, 45)
            sheet.column_dimensions[coluna[0].column_letter].width = largura
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
