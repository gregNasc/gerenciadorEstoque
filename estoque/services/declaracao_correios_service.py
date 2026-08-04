import hashlib
from io import BytesIO
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from estoque.models import (
    DeclaracaoCorreios,
    DeclaracaoCorreiosItem,
    Emprestimo,
    Transferencia,
)


class DeclaracaoCorreiosService:
    MODELO_CORREIOS = (
        Path(__file__).resolve().parent.parent
        / 'assets'
        / 'declaracao_correios_modelo_600dpi.png'
    )
    @staticmethod
    def _endereco(base):
        try:
            endereco = base.endereco_postal
        except ObjectDoesNotExist:
            return {'base_id': base.pk, 'base': base.nome}
        return {
            'base_id': base.pk,
            'base': base.nome,
            'nome_destinatario': endereco.nome_destinatario or base.nome,
            'logradouro': endereco.logradouro,
            'numero': endereco.numero,
            'complemento': endereco.complemento,
            'bairro': endereco.bairro,
            'cidade': endereco.cidade,
            'uf': endereco.uf,
            'cep': endereco.cep,
            'telefone': endereco.telefone,
            'responsavel': endereco.responsavel,
            'documento': endereco.documento,
        }

    @classmethod
    def montar_dados_transferencia(cls, transferencia):
        return {
            'tipo_operacao': DeclaracaoCorreios.TipoOperacao.TRANSFERENCIA,
            'remetente': cls._endereco(transferencia.regional_origem),
            'destinatario': cls._endereco(transferencia.regional_destino),
            'resumo_operacao': {
                'protocolo': transferencia.protocolo,
                'transferencia_id': transferencia.pk,
            },
            'itens': [cls._dados_item(item.equipamento) for item in transferencia.itens.select_related('equipamento__produto') if item.equipamento_id],
        }

    @classmethod
    def montar_dados_emprestimo(cls, emprestimo):
        return {
            'tipo_operacao': DeclaracaoCorreios.TipoOperacao.EMPRESTIMO,
            'remetente': cls._endereco(emprestimo.regional_origem),
            'destinatario': cls._endereco(emprestimo.regional_destino),
            'resumo_operacao': {
                'protocolo': emprestimo.protocolo,
                'emprestimo_id': emprestimo.pk,
            },
            'itens': [cls._dados_item(item.equipamento) for item in emprestimo.itens.select_related('equipamento__produto')],
        }

    @staticmethod
    def _dados_item(equipamento):
        return {
            'equipamento': equipamento,
            'descricao': equipamento.produto.descricao if equipamento.produto else equipamento.codigo,
            'quantidade': 1,
            'valor_unitario': Decimal('0.00'),
            'patrimonio': equipamento.patrimonio,
            'numero_serie': equipamento.numero_serie,
        }

    @classmethod
    @transaction.atomic
    def criar_rascunho(cls, *, usuario, transferencia=None, emprestimo=None):
        if bool(transferencia) == bool(emprestimo):
            raise ValidationError('Informe exatamente uma operação.')
        if transferencia:
            operacao = Transferencia.objects.select_for_update().get(pk=transferencia.pk)
            filtro = {'transferencia': operacao}
            dados = cls.montar_dados_transferencia(operacao)
        else:
            operacao = Emprestimo.objects.select_for_update().get(pk=emprestimo.pk)
            filtro = {'emprestimo': operacao}
            dados = cls.montar_dados_emprestimo(operacao)
        rascunho = DeclaracaoCorreios.objects.filter(
            **filtro,
            status=DeclaracaoCorreios.Status.RASCUNHO,
        ).order_by('-versao').first()
        if rascunho:
            return rascunho
        versao = (DeclaracaoCorreios.objects.filter(**filtro).aggregate(v=Max('versao'))['v'] or 0) + 1
        declaracao = DeclaracaoCorreios.objects.create(
            **filtro,
            tipo_operacao=dados['tipo_operacao'],
            versao=versao,
            remetente=dados['remetente'],
            destinatario=dados['destinatario'],
            resumo_operacao=dados['resumo_operacao'],
            gerada_por=usuario,
        )
        DeclaracaoCorreiosItem.objects.bulk_create([
            DeclaracaoCorreiosItem(declaracao=declaracao, ordem=ordem, **item)
            for ordem, item in enumerate(dados['itens'], start=1)
        ])
        return declaracao

    @staticmethod
    def validar_dados(declaracao):
        erros = []
        campos_endereco = ('logradouro', 'numero', 'bairro', 'cidade', 'uf', 'cep')
        for titulo, endereco in (
            ('remetente', declaracao.remetente),
            ('destinatário', declaracao.destinatario),
        ):
            ausentes = [campo for campo in campos_endereco if not endereco.get(campo)]
            if ausentes:
                erros.append(f'Complete o endereço do {titulo}: {", ".join(ausentes)}.')
        if not declaracao.itens.exists():
            erros.append('A declaração precisa ter ao menos um item.')
        if declaracao.quantidade_volumes < 1:
            erros.append('A quantidade de volumes deve ser maior que zero.')
        if declaracao.peso_total_kg < 0:
            erros.append('O peso total não pode ser negativo.')
        if erros:
            raise ValidationError(erros)

    @staticmethod
    def _formatar_endereco(dados):
        primeira = f"{dados.get('logradouro', '')}, {dados.get('numero', '')}"
        if dados.get('complemento'):
            primeira += f" - {dados['complemento']}"
        return '<br/>'.join(filter(None, [
            dados.get('nome_destinatario') or dados.get('base'),
            primeira,
            f"{dados.get('bairro', '')} - {dados.get('cidade', '')}/{dados.get('uf', '')}",
            f"CEP: {dados.get('cep', '')}",
            f"Responsável: {dados.get('responsavel', '')}" if dados.get('responsavel') else '',
            f"Telefone: {dados.get('telefone', '')}" if dados.get('telefone') else '',
        ]))

    @staticmethod
    def _texto_na_caixa(pdf, texto, x, y, largura, altura, *, tamanho=6.3, negrito=False, alinhamento=TA_LEFT):
        estilo = ParagraphStyle(
            'campo-declaracao',
            fontName='Helvetica-Bold' if negrito else 'Helvetica',
            fontSize=tamanho,
            leading=tamanho + 1,
            alignment=alinhamento,
            spaceAfter=0,
            spaceBefore=0,
        )
        paragrafo = Paragraph(str(texto or '').replace('\n', '<br/>'), estilo)
        _, altura_usada = paragrafo.wrap(largura - 2.2 * mm, altura - 1.2 * mm)
        paragrafo.drawOn(pdf, x + 1.1 * mm, y + altura - altura_usada - 0.7 * mm)

    @classmethod
    def _linha_campo(cls, pdf, x, y_topo, largura, altura, rotulo, valor, *, tamanho=6.6):
        y = y_topo - altura
        pdf.rect(x, y, largura, altura)
        rotulo_largura = pdf.stringWidth(rotulo, 'Helvetica-Bold', tamanho) + 1.7 * mm
        pdf.setFont('Helvetica-Bold', tamanho)
        pdf.drawString(x + 0.8 * mm, y + altura - tamanho - 0.7 * mm, rotulo)
        cls._texto_na_caixa(
            pdf,
            valor,
            x + rotulo_largura,
            y,
            largura - rotulo_largura,
            altura,
            tamanho=tamanho,
        )
        return y

    @classmethod
    def _desenhar_endereco(cls, pdf, x, y_topo, largura, titulo, dados):
        cabecalho = 4 * mm
        pdf.rect(x, y_topo - cabecalho, largura, cabecalho)
        cls._texto_na_caixa(pdf, titulo, x, y_topo - cabecalho, largura, cabecalho, tamanho=7.3, negrito=True, alinhamento=TA_CENTER)
        y = y_topo - cabecalho
        y = cls._linha_campo(pdf, x, y, largura, 5 * mm, 'NOME:', dados.get('nome_destinatario') or dados.get('base', ''))
        endereco = ', '.join(filter(None, [dados.get('logradouro'), dados.get('numero')]))
        complemento = ' - '.join(filter(None, [dados.get('complemento'), dados.get('bairro')]))
        if complemento:
            endereco = f'{endereco}<br/>{complemento}'
        y = cls._linha_campo(pdf, x, y, largura, 9 * mm, 'ENDEREÇO:', endereco, tamanho=6.2)
        altura = 5 * mm
        cidade_largura = largura * 0.78
        cls._linha_campo(pdf, x, y, cidade_largura, altura, 'CIDADE:', dados.get('cidade', ''))
        cls._linha_campo(pdf, x + cidade_largura, y, largura - cidade_largura, altura, 'UF:', dados.get('uf', ''))
        y -= altura
        cep_largura = largura * 0.23
        cls._linha_campo(pdf, x, y, cep_largura, 6 * mm, 'CEP:', dados.get('cep', ''), tamanho=6.2)
        cls._linha_campo(
            pdf,
            x + cep_largura,
            y,
            largura - cep_largura,
            6 * mm,
            'CPF/CNPJ/DOC. ESTRANGEIRO:',
            dados.get('documento', ''),
            tamanho=5.7,
        )

    @classmethod
    def _desenhar_formulario(cls, pdf, declaracao, usuario, itens, y_topo):
        x = 5 * mm
        largura = A4[0] - 10 * mm
        pdf.setLineWidth(0.65)
        titulo_h = 7 * mm
        pdf.rect(x, y_topo - titulo_h, largura, titulo_h)
        cls._texto_na_caixa(pdf, 'DECLARAÇÃO DE CONTEÚDO', x, y_topo - titulo_h, largura, titulo_h, tamanho=11.5, negrito=True, alinhamento=TA_CENTER)
        y = y_topo - titulo_h - 1.5 * mm

        coluna = (largura - 1 * mm) / 2
        cls._desenhar_endereco(pdf, x, y, coluna, 'R E M E T E N T E', declaracao.remetente)
        cls._desenhar_endereco(pdf, x + coluna + 1 * mm, y, coluna, 'D E S T I N A T Á R I O', declaracao.destinatario)
        y -= 29 * mm + 1.5 * mm

        secao_h = 4 * mm
        pdf.rect(x, y - secao_h, largura, secao_h)
        cls._texto_na_caixa(pdf, 'I D E N T I F I C A Ç Ã O   D O S   B E N S', x, y - secao_h, largura, secao_h, tamanho=7.2, negrito=True, alinhamento=TA_CENTER)
        y -= secao_h
        colunas = [14 * mm, 112 * mm, 26 * mm, largura - 152 * mm]
        titulos = ['ITEM', 'CONTEÚDO', 'QUANT.', 'VALOR']
        cursor = x
        for indice, largura_coluna in enumerate(colunas):
            pdf.rect(cursor, y - 4 * mm, largura_coluna, 4 * mm)
            cls._texto_na_caixa(pdf, titulos[indice], cursor, y - 4 * mm, largura_coluna, 4 * mm, tamanho=6.5, negrito=True, alinhamento=TA_CENTER)
            cursor += largura_coluna
        y -= 4 * mm
        for indice in range(4):
            item = itens[indice] if indice < len(itens) else None
            valores = ['', '', '', '']
            if item:
                identidade = ' · '.join(filter(None, [
                    f'Patrimônio {item.patrimonio}' if item.patrimonio else '',
                    f'Série {item.numero_serie}' if item.numero_serie else '',
                ]))
                valores = [
                    str(indice + 1),
                    f'{item.descricao}<br/><font size="5.5">{identidade}</font>' if identidade else item.descricao,
                    str(item.quantidade),
                    f'R$ {item.valor_unitario:.2f}',
                ]
            cursor = x
            for coluna_indice, largura_coluna in enumerate(colunas):
                pdf.rect(cursor, y - 5.5 * mm, largura_coluna, 5.5 * mm)
                cls._texto_na_caixa(
                    pdf, valores[coluna_indice], cursor, y - 5.5 * mm, largura_coluna, 5.5 * mm,
                    tamanho=6.0, alinhamento=TA_CENTER if coluna_indice != 1 else TA_LEFT,
                )
                cursor += largura_coluna
            y -= 5.5 * mm

        quantidade = sum(item.quantidade for item in itens)
        valor_itens = sum(item.quantidade * item.valor_unitario for item in itens)
        valor = declaracao.valor_total_declarado or valor_itens
        total_rotulo_largura = colunas[0] + colunas[1]
        pdf.setFillColor(colors.HexColor('#d0d0d0'))
        pdf.rect(x, y - 5.5 * mm, total_rotulo_largura, 5.5 * mm, fill=1)
        pdf.setFillColor(colors.black)
        cls._texto_na_caixa(pdf, 'TOTAIS', x, y - 5.5 * mm, total_rotulo_largura, 5.5 * mm, tamanho=6.5, negrito=True, alinhamento=TA_RIGHT)
        pdf.rect(x + total_rotulo_largura, y - 5.5 * mm, colunas[2], 5.5 * mm)
        pdf.rect(x + total_rotulo_largura + colunas[2], y - 5.5 * mm, colunas[3], 5.5 * mm)
        cls._texto_na_caixa(pdf, quantidade, x + total_rotulo_largura, y - 5.5 * mm, colunas[2], 5.5 * mm, tamanho=6.5, negrito=True, alinhamento=TA_CENTER)
        cls._texto_na_caixa(pdf, f'R$ {valor:.2f}', x + total_rotulo_largura + colunas[2], y - 5.5 * mm, colunas[3], 5.5 * mm, tamanho=6.5, negrito=True, alinhamento=TA_CENTER)
        y -= 5.5 * mm
        pdf.setFillColor(colors.HexColor('#d0d0d0'))
        pdf.rect(x, y - 5.5 * mm, total_rotulo_largura, 5.5 * mm, fill=1)
        pdf.setFillColor(colors.black)
        cls._texto_na_caixa(pdf, 'PESO TOTAL (kg)', x, y - 5.5 * mm, total_rotulo_largura, 5.5 * mm, tamanho=6.5, negrito=True, alinhamento=TA_RIGHT)
        pdf.rect(x + total_rotulo_largura, y - 5.5 * mm, colunas[2] + colunas[3], 5.5 * mm)
        cls._texto_na_caixa(pdf, f'{declaracao.peso_total_kg:.3f}', x + total_rotulo_largura, y - 5.5 * mm, colunas[2] + colunas[3], 5.5 * mm, tamanho=6.5, alinhamento=TA_CENTER)
        y -= 7 * mm

        declaracao_h = 42 * mm
        pdf.rect(x, y - declaracao_h, largura, declaracao_h)
        pdf.line(x, y - 4 * mm, x + largura, y - 4 * mm)
        cls._texto_na_caixa(pdf, 'D E C L A R A Ç Ã O', x, y - 4 * mm, largura, 4 * mm, tamanho=7.2, negrito=True, alinhamento=TA_CENTER)
        texto_legal = (
            'Declaro que não me enquadro no conceito de contribuinte previsto no art. 4º da Lei Complementar nº 87/1996, '
            'uma vez que não realizo, com habitualidade ou em volume que caracterize intuito comercial, operações de circulação '
            'de mercadoria, ainda que se iniciem no exterior, ou estou dispensado da emissão da nota fiscal por força da legislação '
            'tributária vigente, responsabilizando-me, nos termos da lei e a quem de direito, por informações inverídicas.<br/>'
            'Declaro ainda que não estou postando conteúdo inflamável, explosivo, causador de combustão espontânea, tóxico, corrosivo, '
            'gás ou qualquer outro conteúdo que conste na lista de proibições e restrições disponível no site dos Correios: '
            '<u>https://www.correios.com.br/enviar/proibicoes-e-restricoes/proibicoes-e-restricoes</u>.'
        )
        cls._texto_na_caixa(pdf, texto_legal, x + 1 * mm, y - 29 * mm, largura - 2 * mm, 25 * mm, tamanho=6.1, alinhamento=TA_JUSTIFY)
        cidade = declaracao.remetente.get('cidade', '')
        data = timezone.localdate()
        pdf.setFont('Helvetica', 6.5)
        pdf.drawString(x + 2 * mm, y - 36.5 * mm, f'{cidade}, {data.day:02d} de {data.strftime("%m")} de {data.year}.')
        linha_inicio = x + largura * 0.63
        pdf.line(linha_inicio, y - 35.5 * mm, x + largura - 2 * mm, y - 35.5 * mm)
        cls._texto_na_caixa(pdf, 'Assinatura do Declarante/Remetente', linha_inicio, y - 41 * mm, largura * 0.35, 5 * mm, tamanho=6.2, alinhamento=TA_CENTER)
        y -= declaracao_h + 1.5 * mm

        observacao_h = 10 * mm
        pdf.rect(x, y - observacao_h, largura, observacao_h)
        cls._texto_na_caixa(pdf, '<b>OBSERVAÇÃO:</b><br/>Constitui crime contra a ordem tributária suprimir ou reduzir tributo, ou contribuição social e qualquer acessório (Lei 8.137/90 Art. 1º, V).', x + 1 * mm, y - observacao_h, largura - 2 * mm, observacao_h, tamanho=5.8)
        protocolo = declaracao.resumo_operacao.get('protocolo', '-')
        pdf.setFont('Helvetica', 4.8)
        pdf.drawRightString(x + largura - 1 * mm, y - observacao_h + 1 * mm, f'Protocolo {protocolo} · versão {declaracao.versao}')

    @staticmethod
    def _texto_ajustado(pdf, texto, x, y, largura, *, tamanho=7.0, minimo=4.8, alinhamento='left'):
        texto = str(texto or '').strip()
        fonte = 'Helvetica'
        while tamanho > minimo and pdf.stringWidth(texto, fonte, tamanho) > largura:
            tamanho -= 0.2
        if pdf.stringWidth(texto, fonte, tamanho) > largura:
            while texto and pdf.stringWidth(f'{texto}…', fonte, tamanho) > largura:
                texto = texto[:-1]
            texto = f'{texto}…'
        pdf.setFont(fonte, tamanho)
        if alinhamento == 'center':
            pdf.drawCentredString(x + largura / 2, y, texto)
        elif alinhamento == 'right':
            pdf.drawRightString(x + largura, y, texto)
        else:
            pdf.drawString(x, y, texto)

    @classmethod
    def _desenhar_valores_modelo_oficial(cls, pdf, declaracao, itens):
        altura_pagina = A4[1]

        def y_topo(pontos):
            return altura_pagina - pontos

        enderecos = (
            (declaracao.remetente, 0),
            (declaracao.destinatario, 280.5),
        )
        for dados, deslocamento in enderecos:
            cls._texto_ajustado(
                pdf, dados.get('nome_destinatario') or dados.get('base'),
                44.0 + deslocamento, y_topo(67.0), 234.0, tamanho=7.2,
            )
            endereco = ', '.join(filter(None, [dados.get('logradouro'), dados.get('numero')]))
            complemento = ' - '.join(filter(None, [dados.get('complemento'), dados.get('bairro')]))
            cls._texto_ajustado(pdf, endereco, 64.0 + deslocamento, y_topo(84.0), 210.0, tamanho=6.8)
            cls._texto_ajustado(pdf, complemento, 18.0 + deslocamento, y_topo(98.0), 260.0, tamanho=6.4)
            cls._texto_ajustado(pdf, dados.get('cidade'), 48.0 + deslocamento, y_topo(114.0), 176.0, tamanho=6.8)
            cls._texto_ajustado(pdf, dados.get('uf'), 246.0 + deslocamento, y_topo(114.0), 27.0, tamanho=6.8)
            cls._texto_ajustado(pdf, dados.get('cep'), 35.0 + deslocamento, y_topo(128.0), 47.0, tamanho=6.5)
            # No modelo oficial, o rótulo "CPF/CNPJ/DOC. ESTRANGEIRO:"
            # ocupa quase toda a primeira parte da célula. O valor deve
            # começar somente depois do rótulo para não ficar sobreposto.
            cls._texto_ajustado(
                pdf, dados.get('documento'),
                202.0 + deslocamento, y_topo(128.0), 84.0, tamanho=6.2,
            )

        limites_linhas = [(158.4, 172.8), (172.8, 186.8), (186.8, 200.8), (200.8, 215.2)]
        for indice, (topo, fundo) in enumerate(limites_linhas):
            if indice >= len(itens):
                break
            item = itens[indice]
            cls._texto_ajustado(pdf, indice + 1, 14.0, y_topo(fundo - 9.5), 41.5, tamanho=6.8, alinhamento='center')
            identificacao = ' | '.join(filter(None, [
                f'PAT: {item.patrimonio}' if item.patrimonio else '',
                f'S/N: {item.numero_serie}' if item.numero_serie else '',
            ]))
            estilo = ParagraphStyle(
                f'item-correios-{indice}',
                fontName='Helvetica',
                fontSize=5.5,
                leading=5.8,
                spaceAfter=0,
                spaceBefore=0,
            )
            conteudo = Paragraph(
                f'{escape(item.descricao)}<br/><font size="4.8">{escape(identificacao)}</font>',
                estilo,
            )
            largura_conteudo = 327.0
            altura_linha = fundo - topo
            _, altura_usada = conteudo.wrap(largura_conteudo, altura_linha - 1.2)
            conteudo.drawOn(pdf, 58.0, y_topo(fundo) + max(0.8, (altura_linha - altura_usada) / 2))
            cls._texto_ajustado(pdf, item.quantidade, 387.0, y_topo(fundo - 9.5), 91.0, tamanho=6.8, alinhamento='center')
            cls._texto_ajustado(pdf, f'R$ {item.valor_unitario:.2f}', 480.0, y_topo(fundo - 9.5), 100.0, tamanho=6.5, alinhamento='center')

        quantidade = sum(item.quantidade for item in itens)
        valor_itens = sum(item.quantidade * item.valor_unitario for item in itens)
        valor = declaracao.valor_total_declarado or valor_itens
        cls._texto_ajustado(pdf, quantidade, 387.0, y_topo(225.5), 91.0, tamanho=7.0, alinhamento='center')
        cls._texto_ajustado(pdf, f'R$ {valor:.2f}', 480.0, y_topo(225.5), 100.0, tamanho=7.0, alinhamento='center')
        cls._texto_ajustado(pdf, f'{declaracao.peso_total_kg:.3f}', 387.0, y_topo(240.5), 193.0, tamanho=7.0, alinhamento='center')

        data = timezone.localdate()
        meses = (
            '', 'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
            'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
        )
        cls._texto_ajustado(pdf, declaracao.remetente.get('cidade'), 16.0, y_topo(355.0), 53.0, tamanho=6.8, alinhamento='center')
        cls._texto_ajustado(pdf, f'{data.day:02d}', 120.0, y_topo(355.0), 32.0, tamanho=6.8, alinhamento='center')
        cls._texto_ajustado(pdf, meses[data.month], 168.0, y_topo(355.0), 93.0, tamanho=6.8, alinhamento='center')
        cls._texto_ajustado(pdf, data.year, 274.0, y_topo(355.0), 55.0, tamanho=6.8, alinhamento='center')

    @classmethod
    def _gerar_pdf_modelo_correios(cls, declaracao, usuario):
        if not cls.MODELO_CORREIOS.exists():
            raise ValidationError('O modelo oficial da declaração dos Correios não foi encontrado.')
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
        fundo = ImageReader(str(cls.MODELO_CORREIOS))
        itens = list(declaracao.itens.all())
        paginas = [itens[indice:indice + 4] for indice in range(0, len(itens), 4)] or [[]]
        for itens_pagina in paginas:
            pdf.drawImage(fundo, 0, 0, width=A4[0], height=A4[1], preserveAspectRatio=False, mask='auto')
            cls._desenhar_valores_modelo_oficial(pdf, declaracao, itens_pagina)
            pdf.showPage()
        pdf.save()
        return buffer.getvalue()

    @classmethod
    @transaction.atomic
    def emitir_pdf(cls, declaracao, usuario):
        declaracao = DeclaracaoCorreios.objects.select_for_update().get(pk=declaracao.pk)
        if declaracao.status != DeclaracaoCorreios.Status.RASCUNHO:
            raise ValidationError('Somente rascunhos podem ser emitidos.')
        if declaracao.arquivo:
            raise ValidationError('Esta declaração já possui arquivo e não pode ser sobrescrita.')
        cls.validar_dados(declaracao)
        conteudo = cls._gerar_pdf_modelo_correios(declaracao, usuario)
        protocolo = declaracao.resumo_operacao.get('protocolo', '-')
        declaracao.hash_arquivo = hashlib.sha256(conteudo).hexdigest()
        declaracao.status = DeclaracaoCorreios.Status.EMITIDA
        nome = f'declaracao_{protocolo}_v{declaracao.versao}.pdf'
        declaracao.arquivo.save(nome, ContentFile(conteudo), save=False)
        declaracao.save(update_fields=['arquivo', 'hash_arquivo', 'status'])
        return declaracao

    @classmethod
    @transaction.atomic
    def substituir(cls, declaracao, novos_dados, usuario):
        anterior = DeclaracaoCorreios.objects.select_for_update().get(pk=declaracao.pk)
        if anterior.status != DeclaracaoCorreios.Status.EMITIDA:
            raise ValidationError('Somente declarações emitidas podem ser substituídas.')
        nova = cls.criar_rascunho(
            usuario=usuario,
            transferencia=anterior.transferencia,
            emprestimo=anterior.emprestimo,
        )
        for campo in ('remetente', 'destinatario', 'quantidade_volumes', 'valor_total_declarado', 'observacoes'):
            if campo in novos_dados:
                setattr(nova, campo, novos_dados[campo])
        nova.save()
        anterior.status = DeclaracaoCorreios.Status.SUBSTITUIDA
        anterior.substituida_por = nova
        anterior.save(update_fields=['status', 'substituida_por'])
        return nova

    @staticmethod
    def cancelar(declaracao, usuario, justificativa):
        if declaracao.status == DeclaracaoCorreios.Status.SUBSTITUIDA:
            raise ValidationError('Uma declaração substituída não pode ser cancelada.')
        declaracao.status = DeclaracaoCorreios.Status.CANCELADA
        declaracao.observacoes = '\n'.join(filter(None, [declaracao.observacoes, f'Cancelada por {usuario}: {justificativa}']))
        declaracao.save(update_fields=['status', 'observacoes'])
        return declaracao
