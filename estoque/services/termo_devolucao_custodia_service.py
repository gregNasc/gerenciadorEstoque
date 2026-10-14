from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from estoque.models import DevolucaoCustodia, TermoDevolucaoCustodia


class TermoDevolucaoCustodiaService:
    COR_LARANJA = colors.HexColor('#E37800')
    COR_ESCURO = colors.HexColor('#252A30')
    COR_BORDA = colors.HexColor('#C1C7CE')
    COR_CINZA = colors.HexColor('#F0F1F3')
    COR_SUAVE = colors.HexColor('#657180')

    @classmethod
    def gerar(cls, *, devolucao, usuario):
        if not getattr(devolucao, 'pk', None):
            raise ValidationError({'devolucao': 'Informe uma devolução persistida.'})

        with transaction.atomic():
            devolucao = (
                DevolucaoCustodia.objects.select_for_update()
                .select_related(
                    'custodia__empresa', 'custodia__base',
                    'custodia__colaborador', 'responsavel_recebimento',
                    'registrado_por',
                )
                .prefetch_related('itens__item_custodia')
                .get(pk=devolucao.pk)
            )
            existente = TermoDevolucaoCustodia.objects.filter(
                devolucao=devolucao,
            ).first()
            if existente:
                return existente
            if not usuario or not getattr(usuario, 'is_active', False):
                raise ValidationError({'usuario': 'O usuário gerador deve estar ativo.'})

            registros = list(devolucao.itens.order_by('id'))
            if not registros:
                raise ValidationError({
                    'devolucao': 'O Termo de Devolução exige ao menos um item.',
                })

            snapshot = cls._criar_snapshot(devolucao, registros, timezone.now())
            conteudo = cls.renderizar_pdf(snapshot)
            termo = TermoDevolucaoCustodia(
                devolucao=devolucao,
                dados_snapshot=snapshot,
                sha256=sha256(conteudo).hexdigest(),
                gerado_por=usuario,
            )
            nome = f'termo-devolucao-custodia-{devolucao.pk:06d}.pdf'
            termo.arquivo_pdf.save(nome, ContentFile(conteudo), save=False)
            try:
                termo.save()
            except Exception:
                termo.arquivo_pdf.storage.delete(termo.arquivo_pdf.name)
                raise
            from estoque.models import EventoNotificacaoCustodia
            from estoque.services.custodia_notificacao_service import (
                CustodiaNotificacaoService,
            )

            CustodiaNotificacaoService.publicar(
                evento=EventoNotificacaoCustodia.Evento.TERMO_GERADO,
                custodia=devolucao.custodia,
                criado_por=usuario,
                devolucao=devolucao,
                termo_devolucao=termo,
            )
            return termo

    @staticmethod
    def _criar_snapshot(devolucao, registros, instante):
        custodia = devolucao.custodia
        colaborador = custodia.colaborador
        responsavel = devolucao.responsavel_recebimento
        codigo_custodia = f'CUS-{custodia.data_entrega.year}-{custodia.pk:04d}'
        codigo_devolucao = (
            f'DEV-{devolucao.data_devolucao.year}-{devolucao.pk:04d}'
        )
        itens = []
        for registro in registros:
            item = registro.item_custodia
            tipo = (
                item.categoria_snapshot or 'Equipamento'
                if item.equipamento_id
                else 'Chip / linha móvel'
            )
            itens.append({
                'item_custodia_id': item.pk,
                'tipo': tipo,
                'descricao': item.descricao_snapshot,
                'modelo': item.modelo_snapshot,
                'patrimonio': item.patrimonio_snapshot,
                'numero_serie': item.numero_serie_snapshot,
                'imei': item.imei_snapshot,
                'telefone': item.telefone_snapshot,
                'operadora': item.operadora_snapshot,
                'iccid': item.iccid_snapshot,
                'situacao': registro.get_situacao_display(),
                'condicao_devolucao': (
                    registro.get_condicao_devolucao_display()
                    if registro.condicao_devolucao != 'NAO_INFORMADA'
                    else ''
                ),
                'observacao': registro.observacao,
            })
        return {
            'schema_version': 1,
            'modelo_documento': 'devolucao_custodia_v1',
            'gerado_em': instante.isoformat(),
            'devolucao': {
                'id': devolucao.pk,
                'codigo': codigo_devolucao,
                'data': devolucao.data_devolucao.isoformat(),
                'motivo': devolucao.motivo,
                'observacao': devolucao.observacao,
            },
            'custodia': {
                'id': custodia.pk,
                'codigo': codigo_custodia,
                'data_entrega': custodia.data_entrega.isoformat(),
                'status': custodia.get_status_display(),
            },
            'empresa': {'id': custodia.empresa_id, 'nome': custodia.empresa.nome},
            'base': {'id': custodia.base_id, 'nome': custodia.base.nome},
            'colaborador': {
                'id': colaborador.pk,
                'nome': colaborador.nome,
                'matricula': colaborador.matricula,
                'setor': colaborador.setor,
                'cargo_funcao': colaborador.cargo_funcao,
            },
            'responsavel_recebimento': {
                'id': responsavel.pk,
                'nome': responsavel.nome,
            },
            'responsavel_registro': {
                'id': devolucao.registrado_por_id,
                'nome': (
                    devolucao.registrado_por.get_full_name()
                    or devolucao.registrado_por.get_username()
                ),
            },
            'itens': itens,
        }

    @classmethod
    def renderizar_pdf(cls, snapshot):
        buffer = BytesIO()
        devolucao = snapshot['devolucao']
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=17 * mm,
            leftMargin=17 * mm,
            topMargin=16 * mm,
            bottomMargin=15 * mm,
            title=f'Termo de Devolução - {devolucao["codigo"]}',
            author='gerenciadorEstoque',
            subject='Registro automático de devolução de ativos em Custódia',
        )
        styles = cls._estilos()
        itens = snapshot['itens']
        devolvidos = sum(item['situacao'].casefold() == 'devolvido' for item in itens)
        faltantes = len(itens) - devolvidos
        story = [
            Paragraph('TERMO DE DEVOLUÇÃO DE ATIVOS EM CUSTÓDIA', styles['Titulo']),
            cls._tabela_identificacao(snapshot, styles),
            Paragraph('1. ITENS DA DEVOLUÇÃO', styles['Secao']),
            cls._tabela_itens(itens, styles),
            Spacer(1, 3 * mm),
            cls._tabela_resumo(devolvidos, faltantes, styles),
            Paragraph('2. MOTIVO E OBSERVAÇÕES', styles['Secao']),
            cls._tabela_motivo(snapshot, styles),
            Paragraph('3. DECLARAÇÃO DE DEVOLUÇÃO', styles['Secao']),
            Paragraph(
                'As partes confirmam que os itens relacionados foram conferidos '
                'e classificados conforme a situação e a condição registradas '
                'neste documento. Itens faltantes permanecem vinculados à Custódia '
                'até sua devolução formal ou tratamento posterior autorizado.',
                styles['Corpo'],
            ),
            Paragraph('4. CIÊNCIA E ACEITE', styles['Secao']),
            cls._bloco_assinaturas(snapshot, styles),
            Spacer(1, 3 * mm),
            cls._bloco_testemunha(styles),
            Spacer(1, 2 * mm),
            Paragraph(
                'Assinatura eletrônica: este documento está preparado para o fluxo '
                'DocuSign. O identificador do envelope e o arquivo assinado serão '
                'registrados no gerenciadorEstoque em etapa própria.',
                styles['Nota'],
            ),
            Paragraph('5. CONTROLE INTERNO', styles['Secao']),
            cls._tabela_controle(snapshot, styles),
        ]

        def cabecalho_rodape(canvas, documento):
            canvas.saveState()
            largura, altura = A4
            canvas.setFillColor(cls.COR_LARANJA)
            canvas.rect(0, altura - 6 * mm, largura, 6 * mm, stroke=0, fill=1)
            canvas.setStrokeColor(colors.HexColor('#D5DAE0'))
            canvas.setLineWidth(.4)
            canvas.line(18 * mm, 14 * mm, largura - 18 * mm, 14 * mm)
            canvas.setFont('Helvetica', 7.5)
            canvas.setFillColor(cls.COR_SUAVE)
            canvas.drawRightString(
                largura - 18 * mm, 9 * mm, f'Página {documento.page}',
            )
            canvas.restoreState()

        doc.build(story, onFirstPage=cabecalho_rodape, onLaterPages=cabecalho_rodape)
        return buffer.getvalue()

    @classmethod
    def _estilos(cls):
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='Titulo', parent=styles['Title'], fontName='Helvetica-Bold',
            fontSize=15, leading=17, textColor=cls.COR_ESCURO,
            alignment=TA_CENTER, spaceAfter=5 * mm,
        ))
        styles.add(ParagraphStyle(
            name='Corpo', parent=styles['Normal'], fontName='Helvetica',
            fontSize=8.7, leading=11, textColor=cls.COR_ESCURO,
            spaceAfter=1.5 * mm,
        ))
        styles.add(ParagraphStyle(
            name='Secao', parent=styles['Heading2'], fontName='Helvetica-Bold',
            fontSize=10.6, leading=13, textColor=cls.COR_ESCURO,
            spaceBefore=2 * mm, spaceAfter=1.5 * mm,
        ))
        styles.add(ParagraphStyle(
            name='Celula', parent=styles['Normal'], fontSize=8,
            leading=9.8, textColor=cls.COR_ESCURO,
        ))
        styles.add(ParagraphStyle(
            name='Cabecalho', parent=styles['Celula'], fontName='Helvetica-Bold',
            textColor=colors.white,
        ))
        styles.add(ParagraphStyle(
            name='Nota', parent=styles['Corpo'], fontSize=7.8,
            leading=10, textColor=cls.COR_SUAVE,
        ))
        styles.add(ParagraphStyle(
            name='Devolvido', parent=styles['Celula'], fontName='Helvetica-Bold',
            textColor=colors.HexColor('#147A3D'),
        ))
        styles.add(ParagraphStyle(
            name='Faltante', parent=styles['Celula'], fontName='Helvetica-Bold',
            textColor=colors.HexColor('#B42318'),
        ))
        return styles

    @classmethod
    def _tabela_identificacao(cls, snapshot, styles):
        data = timezone.datetime.fromisoformat(snapshot['devolucao']['data'])
        if timezone.is_aware(data):
            data = timezone.localtime(data)
        linhas = [
            ['Devolução', snapshot['devolucao']['codigo'], 'Data', data.strftime('%d/%m/%Y %H:%M')],
            ['Custódia', snapshot['custodia']['codigo'], 'Status', snapshot['custodia']['status']],
            ['Empresa', snapshot['empresa']['nome'], 'Base / Local', snapshot['base']['nome']],
            ['Colaborador', snapshot['colaborador']['nome'], 'Matrícula', snapshot['colaborador']['matricula'] or '-'],
            ['Recebido por', snapshot['responsavel_recebimento']['nome'], 'Registrado por', snapshot['responsavel_registro']['nome']],
        ]
        tabela = Table(linhas, colWidths=[30 * mm, 58 * mm, 33 * mm, 55 * mm])
        tabela.setStyle(cls._estilo_grade(rotulos=(0, 2)))
        return tabela

    @classmethod
    def _tabela_itens(cls, itens, styles):
        cabecalho = ['Item', 'Identificação', 'Registro da devolução', 'Resultado']
        linhas = [[Paragraph(c, styles['Cabecalho']) for c in cabecalho]]
        for item in itens:
            nome = f'<b>{escape(item["tipo"])}</b>'
            if item['modelo']:
                nome += f'<br/>{escape(item["modelo"])}'
            identificacao = []
            for rotulo, valor in (
                ('Patrimônio', item['patrimonio']), ('Série', item['numero_serie']),
                ('IMEI', item['imei']), ('Linha', item['telefone']),
                ('ICCID', item['iccid']),
            ):
                if valor:
                    identificacao.append(f'{rotulo}: {escape(valor)}')
            registro = []
            if item['condicao_devolucao']:
                registro.append(f'Condição: {escape(item["condicao_devolucao"])}')
            if item['observacao']:
                registro.append(escape(item['observacao']))
            estilo_resultado = (
                styles['Devolvido']
                if item['situacao'].casefold() == 'devolvido'
                else styles['Faltante']
            )
            linhas.append([
                Paragraph(nome, styles['Celula']),
                Paragraph('<br/>'.join(identificacao) or '-', styles['Celula']),
                Paragraph('<br/>'.join(registro) or '-', styles['Celula']),
                Paragraph(escape(item['situacao']), estilo_resultado),
            ])
        tabela = Table(
            linhas, repeatRows=1,
            colWidths=[37 * mm, 52 * mm, 57 * mm, 30 * mm],
        )
        tabela.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), .3, cls.COR_BORDA),
            ('BACKGROUND', (0, 0), (-1, 0), cls.COR_ESCURO),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7F7F8')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return tabela

    @classmethod
    def _tabela_resumo(cls, devolvidos, faltantes, styles):
        dados = [[
            Paragraph('<b>Total classificado</b>', styles['Celula']),
            Paragraph(str(devolvidos + faltantes), styles['Celula']),
            Paragraph('<b>Devolvidos</b>', styles['Celula']),
            Paragraph(str(devolvidos), styles['Devolvido']),
            Paragraph('<b>Faltantes</b>', styles['Celula']),
            Paragraph(str(faltantes), styles['Faltante']),
        ]]
        tabela = Table(dados, colWidths=[35 * mm, 18 * mm, 29 * mm, 18 * mm, 29 * mm, 18 * mm])
        tabela.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), .3, cls.COR_BORDA),
            ('INNERGRID', (0, 0), (-1, -1), .3, cls.COR_BORDA),
            ('BACKGROUND', (0, 0), (-1, -1), cls.COR_CINZA),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        return tabela

    @classmethod
    def _tabela_motivo(cls, snapshot, styles):
        linhas = [
            ['Motivo', snapshot['devolucao']['motivo']],
            ['Observações', snapshot['devolucao']['observacao'] or '-'],
        ]
        dados = [[
            Paragraph(f'<b>{escape(rotulo)}</b>', styles['Celula']),
            Paragraph(escape(valor), styles['Celula']),
        ] for rotulo, valor in linhas]
        tabela = Table(dados, colWidths=[32 * mm, 144 * mm])
        tabela.setStyle(cls._estilo_grade(rotulos=(0,)))
        return tabela

    @classmethod
    def _bloco_assinaturas(cls, snapshot, styles):
        data = timezone.datetime.fromisoformat(snapshot['devolucao']['data'])
        if timezone.is_aware(data):
            data = timezone.localtime(data)
        data_texto = data.strftime('%d/%m/%Y')
        linhas = [
            [
                Paragraph('<b>COLABORADOR / CUSTODIANTE</b>', styles['Celula']),
                Paragraph('<b>RESPONSÁVEL PELO RECEBIMENTO</b>', styles['Celula']),
            ],
            [
                Paragraph(
                    f'{escape(snapshot["colaborador"]["nome"])}<br/><br/>'
                    f'Assinatura: ___________________________<br/>Data: {data_texto}',
                    styles['Celula'],
                ),
                Paragraph(
                    f'{escape(snapshot["responsavel_recebimento"]["nome"])}<br/><br/>'
                    f'Assinatura: ___________________________<br/>Data: {data_texto}',
                    styles['Celula'],
                ),
            ],
        ]
        tabela = Table(linhas, colWidths=[88 * mm, 88 * mm])
        tabela.setStyle(cls._estilo_grade(rotulos=(), primeira_linha=True))
        return tabela

    @classmethod
    def _bloco_testemunha(cls, styles):
        linhas = [[
            Paragraph('<b>TESTEMUNHA - DEPARTAMENTO PESSOAL</b>', styles['Celula']),
        ], [
            Paragraph(
                'Nome: ________________________________________________<br/>'
                'E-mail: _______________________________________________<br/><br/>'
                'Assinatura: ____________________________________________<br/>'
                'Data: ____/____/________',
                styles['Celula'],
            ),
        ]]
        tabela = Table(linhas, colWidths=[176 * mm])
        tabela.setStyle(cls._estilo_grade(rotulos=(), primeira_linha=True))
        return tabela

    @classmethod
    def _tabela_controle(cls, snapshot, styles):
        linhas = [
            ['Origem', 'gerenciadorEstoque', 'ID da devolução', snapshot['devolucao']['codigo']],
            ['Custódia', snapshot['custodia']['codigo'], 'Registrado por', snapshot['responsavel_registro']['nome']],
        ]
        dados = []
        for linha in linhas:
            dados.append([
                Paragraph(
                    f'<b>{escape(str(valor))}</b>' if indice in (0, 2) else escape(str(valor)),
                    styles['Celula'],
                )
                for indice, valor in enumerate(linha)
            ])
        tabela = Table(dados, colWidths=[28 * mm, 48 * mm, 42 * mm, 58 * mm])
        tabela.setStyle(cls._estilo_grade(rotulos=(0, 2)))
        return tabela

    @classmethod
    def _estilo_grade(cls, *, rotulos, primeira_linha=False):
        comandos = [
            ('GRID', (0, 0), (-1, -1), .3, cls.COR_BORDA),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        for coluna in rotulos:
            comandos.append(('BACKGROUND', (coluna, 0), (coluna, -1), cls.COR_CINZA))
        if primeira_linha:
            comandos.append(('BACKGROUND', (0, 0), (-1, 0), cls.COR_CINZA))
        return TableStyle(comandos)
