from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from estoque.models import Custodia, TermoEntregaCustodia


class TermoEntregaCustodiaService:
    COR_PRIMARIA = colors.HexColor('#173B6C')
    COR_SECUNDARIA = colors.HexColor('#EAF0F8')
    COR_TEXTO_SUAVE = colors.HexColor('#52606D')

    @classmethod
    def gerar(cls, *, custodia, usuario):
        if not getattr(custodia, 'pk', None):
            raise ValidationError({'custodia': 'Informe uma Custódia persistida.'})

        with transaction.atomic():
            custodia = (
                Custodia.objects.select_for_update()
                .select_related('empresa', 'base', 'colaborador', 'registrado_por')
                .prefetch_related('itens')
                .get(pk=custodia.pk)
            )
            existente = TermoEntregaCustodia.objects.filter(
                custodia=custodia,
            ).first()
            if existente:
                return existente

            if custodia.status not in (
                Custodia.Status.ATIVA,
                Custodia.Status.EM_DEVOLUCAO,
                Custodia.Status.FINALIZADA,
            ):
                raise ValidationError({
                    'custodia': 'O Termo de Entrega exige uma Custódia ativada.',
                })

            itens = list(custodia.itens.order_by('id'))
            if not itens:
                raise ValidationError({
                    'custodia': 'O Termo de Entrega exige ao menos um item.',
                })
            if not usuario or not getattr(usuario, 'is_active', False):
                raise ValidationError({'usuario': 'O usuário gerador deve estar ativo.'})

            instante = timezone.now()
            snapshot = cls._criar_snapshot(custodia, itens, instante)
            conteudo = cls.renderizar_pdf(snapshot)
            termo = TermoEntregaCustodia(
                custodia=custodia,
                dados_snapshot=snapshot,
                sha256=sha256(conteudo).hexdigest(),
                gerado_por=usuario,
            )
            nome = f'termo-entrega-custodia-{custodia.pk:06d}.pdf'
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
                custodia=custodia,
                criado_por=usuario,
                termo_entrega=termo,
            )
            return termo

    @staticmethod
    def _criar_snapshot(custodia, itens, instante):
        dados_itens = []
        for item in itens:
            tipo = (
                item.categoria_snapshot or 'Equipamento'
                if item.equipamento_id
                else 'Chip / linha móvel'
            )
            dados_itens.append({
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
                'condicao_entrega': item.get_condicao_entrega_display(),
                'observacao_entrega': item.observacao,
            })
        colaborador = custodia.colaborador
        registrador = custodia.registrado_por
        codigo = f'CUS-{custodia.data_entrega.year}-{custodia.pk:04d}'
        return {
            'schema_version': 2,
            'modelo_documento': 'custodia_responsabilidade_v2',
            'gerado_em': instante.isoformat(),
            'custodia': {
                'id': custodia.pk,
                'codigo': codigo,
                'data_entrega': custodia.data_entrega.isoformat(),
                'status': custodia.get_status_display(),
            },
            'empresa': {
                'id': custodia.empresa_id,
                'nome': custodia.empresa.nome,
            },
            'base': {
                'id': custodia.base_id,
                'nome': custodia.base.nome,
            },
            'colaborador': {
                'id': colaborador.pk,
                'nome': colaborador.nome,
                'matricula': colaborador.matricula,
                'cargo_funcao': colaborador.cargo_funcao,
                'setor': colaborador.setor,
            },
            'responsavel_registro': {
                'id': registrador.pk,
                'nome': registrador.get_full_name() or registrador.get_username(),
            },
            'itens': dados_itens,
        }

    @classmethod
    def renderizar_pdf(cls, snapshot):
        buffer = BytesIO()
        custodia_id = snapshot['custodia']['id']
        codigo = snapshot['custodia'].get(
            'codigo',
            f'CUS-{snapshot["custodia"]["data_entrega"][:4]}-{custodia_id:04d}',
        )
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=17 * mm,
            leftMargin=17 * mm,
            topMargin=21 * mm,
            bottomMargin=19 * mm,
            title=f'Termo de Custódia e Responsabilidade - {codigo}',
            author='gerenciadorEstoque',
            subject='Registro automático de entrega e responsabilidade de ativos',
        )
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='TermoTitulo',
            parent=styles['Title'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=18,
            textColor=colors.HexColor('#252A30'),
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ))
        styles.add(ParagraphStyle(
            name='TermoCorpo',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.2,
            leading=12.2,
            textColor=colors.HexColor('#252A30'),
            spaceAfter=2.2 * mm,
        ))
        styles.add(ParagraphStyle(
            name='TermoSecao',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=11.2,
            leading=14,
            textColor=colors.HexColor('#252A30'),
            spaceBefore=3.5 * mm,
            spaceAfter=2.2 * mm,
        ))
        styles.add(ParagraphStyle(
            name='TermoCelula',
            parent=styles['Normal'],
            fontSize=8,
            leading=9.8,
            textColor=colors.HexColor('#252A30'),
        ))
        styles.add(ParagraphStyle(
            name='TermoCabecalho',
            parent=styles['TermoCelula'],
            fontName='Helvetica-Bold',
            textColor=colors.white,
        ))
        styles.add(ParagraphStyle(
            name='TermoCentro',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
        ))
        styles.add(ParagraphStyle(
            name='TermoNota',
            parent=styles['TermoCorpo'],
            fontSize=7.8,
            leading=10,
            textColor=colors.HexColor('#657180'),
        ))
        styles.add(ParagraphStyle(
            name='TermoEstado',
            parent=styles['TermoCelula'],
            textColor=colors.HexColor('#147A3D'),
        ))

        story = [
            Paragraph(
                'TERMO DE CUSTÓDIA E RESPONSABILIDADE DE<br/>EQUIPAMENTOS',
                styles['TermoTitulo'],
            ),
            cls._tabela_identificacao(snapshot, styles),
            Paragraph('1. ITENS ENTREGUES EM CUSTÓDIA', styles['TermoSecao']),
            cls._tabela_itens(snapshot['itens'], styles),
            Paragraph('2. DECLARAÇÃO DE RECEBIMENTO', styles['TermoSecao']),
            Paragraph(
                'O colaborador declara ter recebido os itens acima identificados em '
                'condições adequadas de uso, comprometendo-se a mantê-los sob sua '
                'guarda e responsabilidade enquanto permanecerem em sua custódia, '
                'observando as políticas internas da empresa e a finalidade '
                'profissional para a qual foram disponibilizados.',
                styles['TermoCorpo'],
            ),
            Paragraph('3. CONDIÇÕES DE USO E RESPONSABILIDADE', styles['TermoSecao']),
            *cls._condicoes_uso(styles),
            cls._aviso_seguranca(styles),
            PageBreak(),
            Paragraph('4. DEVOLUÇÃO E ENCERRAMENTO DA CUSTÓDIA', styles['TermoSecao']),
            Paragraph(
                'A devolução deverá ser formalizada no sistema, com data, condição '
                'de cada item, observações, eventuais divergências e identificação '
                'do responsável pelo recebimento. A Custódia permanecerá ativa até '
                'a confirmação formal da devolução dos itens vinculados.',
                styles['TermoCorpo'],
            ),
            cls._tabela_previsao_devolucao(styles),
            Paragraph('5. CIÊNCIA E ACEITE', styles['TermoSecao']),
            Paragraph(
                'O colaborador declara que conferiu os itens e dados relacionados '
                'neste termo e está ciente das responsabilidades decorrentes da '
                'Custódia. A empresa registra a entrega dos ativos descritos e '
                'mantém o histórico de movimentações, vínculos e devoluções.',
                styles['TermoCorpo'],
            ),
            cls._bloco_assinaturas(snapshot, styles),
            Spacer(1, 3 * mm),
            cls._bloco_testemunha(styles),
            Spacer(1, 2 * mm),
            Paragraph(
                'Assinatura eletrônica: este documento está preparado para o fluxo '
                'DocuSign, mantendo o colaborador como signatário e o Departamento '
                'Pessoal como testemunha. O identificador do envelope e o documento '
                'assinado serão registrados no gerenciadorEstoque em etapa própria.',
                styles['TermoNota'],
            ),
            Paragraph('6. CONTROLE INTERNO', styles['TermoSecao']),
            cls._tabela_controle_interno(snapshot, styles),
        ]

        def cabecalho_rodape(canvas, documento):
            canvas.saveState()
            largura, altura = A4
            canvas.setFillColor(colors.HexColor('#E37800'))
            canvas.rect(0, altura - 6 * mm, largura, 6 * mm, stroke=0, fill=1)
            canvas.setStrokeColor(colors.HexColor('#D5DAE0'))
            canvas.setLineWidth(.4)
            canvas.line(18 * mm, 14 * mm, largura - 18 * mm, 14 * mm)
            canvas.setFont('Helvetica', 7.5)
            canvas.setFillColor(cls.COR_TEXTO_SUAVE)
            canvas.drawRightString(
                largura - 18 * mm,
                9 * mm,
                f'Página {documento.page}',
            )
            canvas.restoreState()

        doc.build(
            story,
            onFirstPage=cabecalho_rodape,
            onLaterPages=cabecalho_rodape,
        )
        return buffer.getvalue()

    @classmethod
    def _tabela_identificacao(cls, snapshot, styles):
        colaborador = snapshot['colaborador']
        custodia = snapshot['custodia']
        data = timezone.datetime.fromisoformat(custodia['data_entrega']).strftime('%d/%m/%Y')
        codigo = custodia.get(
            'codigo', f'CUS-{custodia["data_entrega"][:4]}-{custodia["id"]:04d}',
        )
        linhas = [
            ['Termo', codigo, 'Data de entrega', data],
            ['Empresa', snapshot['empresa']['nome'], 'Base / Local', snapshot['base']['nome']],
            ['Colaborador', colaborador['nome'], 'Setor', colaborador['setor'] or '-'],
            ['Matrícula', colaborador['matricula'] or '-', 'Função', colaborador['cargo_funcao'] or '-'],
        ]
        tabela = Table(linhas, colWidths=[30 * mm, 58 * mm, 33 * mm, 55 * mm])
        tabela.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#C5CBD2')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0F1F3')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F0F1F3')),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('LEADING', (0, 0), (-1, -1), 10.5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        return tabela

    @classmethod
    def _tabela_itens(cls, itens, styles):
        cabecalho = ['Item', 'Identificação', 'Dados complementares', 'Estado']
        linhas = [[Paragraph(escape(c), styles['TermoCabecalho']) for c in cabecalho]]
        for item in itens:
            nome = f'<b>{escape(item["tipo"])}</b>'
            if item['modelo']:
                nome += f'<br/>{escape(item["modelo"])}'
            elif item['descricao'] and item['descricao'].casefold() != 'linha móvel'.casefold():
                nome += f'<br/>{escape(item["descricao"])}'

            identificacao = []
            if item['patrimonio']:
                identificacao.append(f'Patrimônio: {escape(item["patrimonio"])}')
            if item['numero_serie']:
                identificacao.append(f'Série: {escape(item["numero_serie"])}')
            if item['telefone']:
                identificacao.append(f'Linha: {escape(item["telefone"])}')
            if item['iccid']:
                identificacao.append(f'ICCID: {escape(item["iccid"])}')

            complementares = []
            if item['imei']:
                complementares.append(f'IMEI: {escape(item["imei"])}')
            if item['operadora']:
                complementares.append(f'Operadora: {escape(item["operadora"])}')
            if item.get('observacao_entrega'):
                complementares.append(escape(item['observacao_entrega']))
            if item['telefone']:
                complementares.append('Credenciais móveis mantidas em cadastro restrito.')

            estado = f'<b>{escape(item["condicao_entrega"])}</b>'
            linhas.append([
                Paragraph(nome, styles['TermoCelula']),
                Paragraph('<br/>'.join(identificacao) or '-', styles['TermoCelula']),
                Paragraph('<br/>'.join(complementares) or '-', styles['TermoCelula']),
                Paragraph(estado, styles['TermoEstado']),
            ])
        tabela = Table(
            linhas,
            repeatRows=1,
            colWidths=[34 * mm, 49 * mm, 63 * mm, 30 * mm],
        )
        tabela.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#C1C7CE')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#252A30')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7F7F8')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        return tabela

    @staticmethod
    def _condicoes_uso(styles):
        textos = [
            '3.1. Utilizar os equipamentos e a linha móvel prioritariamente para atividades profissionais autorizadas, preservando sua integridade física, lógica e funcional.',
            '3.2. Não ceder, emprestar, transferir ou entregar qualquer item a terceiro sem autorização e registro formal da empresa.',
            '3.3. Comunicar imediatamente perda, furto, roubo, dano, defeito, quebra, indisponibilidade da linha ou suspeita de comprometimento de segurança, seguindo os procedimentos internos aplicáveis.',
            '3.4. Não remover controles de segurança, perfis corporativos, aplicativos de gestão, etiquetas patrimoniais ou mecanismos de identificação sem autorização.',
            '3.5. Qualquer substituição de chip ou linha móvel deve ser formalmente registrada, preservando o histórico de vínculo com o equipamento.',
            '3.6. Os itens deverão ser devolvidos quando solicitados, em caso de troca de função, transferência, desligamento ou quando cessar a necessidade de uso, consideradas as condições decorrentes do uso normal.',
            '3.7. O colaborador deverá disponibilizar os ativos para inspeção, inventário, manutenção, atualização ou substituição quando solicitado pela empresa.',
        ]
        return [Paragraph(texto, styles['TermoCorpo']) for texto in textos]

    @staticmethod
    def _aviso_seguranca(styles):
        aviso = Paragraph(
            'Observação de segurança: senhas, PIN, PIN 2, PUK e PUK 2 não '
            'constam neste termo nem em documentos de circulação ampla. Esses '
            'dados permanecem protegidos em área restrita do sistema.',
            styles['TermoNota'],
        )
        tabela = Table([[aviso]], colWidths=[176 * mm])
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFF8EF')),
            ('BOX', (0, 0), (-1, -1), .5, colors.HexColor('#E7A760')),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        return tabela

    @staticmethod
    def _tabela_previsao_devolucao(styles):
        linhas = [
            ['Data prevista de devolução', 'Indeterminada - enquanto durar a necessidade de uso'],
            ['Data efetiva de devolução', '__________________________________________'],
            ['Condição na devolução', '__________________________________________'],
            ['Observações', '__________________________________________<br/>__________________________________________'],
        ]
        dados = []
        for rotulo, valor in linhas:
            dados.append([
                Paragraph(f'<b>{escape(rotulo)}</b>', styles['TermoCelula']),
                Paragraph(valor, styles['TermoCelula']),
            ])
        tabela = Table(dados, colWidths=[55 * mm, 121 * mm])
        tabela.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#C1C7CE')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0F1F3')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        return tabela

    @classmethod
    def _bloco_assinaturas(cls, snapshot, styles):
        colaborador = escape(snapshot['colaborador']['nome'])
        responsavel = escape(snapshot.get('responsavel_registro', {}).get('nome') or snapshot['empresa']['nome'])
        data = timezone.datetime.fromisoformat(
            snapshot['custodia']['data_entrega'],
        ).strftime('%d/%m/%Y')
        assinatura = Table([
            [
                Paragraph('<b>COLABORADOR / CUSTODIANTE</b>', styles['TermoCelula']),
                Paragraph('<b>RESPONSÁVEL PELA ENTREGA</b>', styles['TermoCelula']),
            ],
            [
                Paragraph(
                    f'{colaborador}<br/><br/>Assinatura: ___________________________<br/>Data: {data}',
                    styles['TermoCelula'],
                ),
                Paragraph(
                    f'{responsavel}<br/><br/>Assinatura: ___________________________<br/>Data: {data}',
                    styles['TermoCelula'],
                ),
            ],
        ], colWidths=[88 * mm, 88 * mm])
        assinatura.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#C1C7CE')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0F1F3')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        return assinatura

    @staticmethod
    def _bloco_testemunha(styles):
        cabecalho = Paragraph(
            '<b>TESTEMUNHA - DEPARTAMENTO PESSOAL</b>',
            styles['TermoCelula'],
        )
        corpo = Paragraph(
            'Nome: ________________________________________________<br/>'
            'E-mail: _______________________________________________<br/><br/>'
            'Assinatura: ____________________________________________<br/>'
            'Data: ____/____/________',
            styles['TermoCelula'],
        )
        tabela = Table([[cabecalho], [corpo]], colWidths=[176 * mm])
        tabela.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#C1C7CE')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0F1F3')),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        return tabela

    @staticmethod
    def _tabela_controle_interno(snapshot, styles):
        custodia = snapshot['custodia']
        responsavel = snapshot.get('responsavel_registro', {}).get('nome', '-')
        codigo = custodia.get(
            'codigo', f'CUS-{custodia["data_entrega"][:4]}-{custodia["id"]:04d}',
        )
        linhas = [
            ['Status', custodia.get('status', 'Ativa'), 'Responsável pelo registro', responsavel],
            ['Origem', 'gerenciadorEstoque', 'ID interno', codigo],
        ]
        dados = []
        for linha in linhas:
            dados.append([
                Paragraph(f'<b>{escape(str(valor))}</b>', styles['TermoCelula'])
                if indice in (0, 2)
                else Paragraph(escape(str(valor)), styles['TermoCelula'])
                for indice, valor in enumerate(linha)
            ])
        tabela = Table(dados, colWidths=[28 * mm, 45 * mm, 47 * mm, 56 * mm])
        tabela.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#C1C7CE')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0F1F3')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F0F1F3')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        return tabela
