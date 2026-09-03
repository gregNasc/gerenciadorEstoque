import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import gettext as _

from estoque.services.manual_service import ManualService


class DocumentationService:
    """Catálogo unificado sem retirar a compatibilidade com ManualService."""

    CATALOGO = Path(__file__).resolve().parent.parent / 'data' / 'documentacao.json'
    CATALOGO_ES = Path(__file__).resolve().parent.parent / 'data' / 'documentacao_es.json'
    STATIC_ROOT = Path(settings.BASE_DIR) / 'estoque' / 'static'
    TIPOS = {
        'MANUAL_OFICIAL': 'Manual oficial',
        'RESOLUCAO': 'Resolução de problemas',
        'CHECKLIST_CLIENTE': 'Checklist de cliente',
        'VIDEO': 'Vídeo',
        'DRIVER_FIRMWARE': 'Driver e firmware',
    }
    MARCADORES_RESOLUCAO = (
        'resolucao', 'resolver', 'problema', 'defeito', 'falha', 'erro', 'offline',
        'codigo 43', 'usb', 'nao imprime', 'nao puxa', 'atolamento', 'paper jam',
        'toner', 'cartucho', 'qualidade', 'led', 'fila presa', 'out of paper',
    )
    MARCADORES_CHECKLIST = (
        'o que entregamos', 'o que entregar', 'entregaveis', 'entregavel',
        'relatorio do cliente', 'relatorios do cliente', 'checklist do cliente',
    )
    CLIENTE_ALIASES = {'oxxo': 'oxx', 'assai': 'asi'}

    @staticmethod
    def _youtube_embed_url(url):
        """Converte URLs conhecidas do YouTube em uma URL segura de incorporação."""
        try:
            parsed = urlparse(url)
        except (TypeError, ValueError):
            return ''

        host = (parsed.hostname or '').lower().rstrip('.')
        path_parts = [part for part in parsed.path.split('/') if part]
        video_id = ''

        if host in {'youtu.be', 'www.youtu.be'} and path_parts:
            video_id = path_parts[0]
        elif host in {
            'youtube.com', 'www.youtube.com', 'm.youtube.com',
            'music.youtube.com', 'youtube-nocookie.com',
            'www.youtube-nocookie.com',
        }:
            if parsed.path.rstrip('/') == '/watch':
                video_id = parse_qs(parsed.query).get('v', [''])[0]
            elif len(path_parts) >= 2 and path_parts[0] in {'embed', 'shorts', 'live'}:
                video_id = path_parts[1]

        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            return ''
        return f'https://www.youtube-nocookie.com/embed/{video_id}'

    @classmethod
    @lru_cache(maxsize=1)
    def _documentos_json(cls):
        documentos = []
        for catalogo in (cls.CATALOGO, cls.CATALOGO_ES):
            with catalogo.open(encoding='utf-8') as arquivo:
                dados = json.load(arquivo)
            for item in dados.get('documentos', []):
                documento = dict(item)
                # Compatibilidade com um erro de grafia de catálogos importados.
                documento['tipo_documento'] = documento.get(
                    'tipo_documento', documento.pop('tipo_documentO', '')
                )
                documentos.append(documento)
        return documentos

    @classmethod
    def _manual_como_documento(cls, manual, indice):
        return {
            'id': f"manual-{indice:03d}-{ManualService.normalizar(manual.get('produto_codigo')).replace(' ', '-')}",
            'tipo_documento': 'MANUAL_OFICIAL',
            'produto_codigo': manual.get('produto_codigo', ''),
            'produto': manual.get('produto', ''),
            'cliente_sigla': '',
            'categoria': manual.get('categoria', ''),
            'fabricante': manual.get('fabricante', ''),
            'modelo': manual.get('modelo', ''),
            'titulo': manual.get('titulo', ''),
            'resumo': manual.get('resumo', ''),
            'arquivo': manual.get('arquivo', ''),
            'texto': manual.get('texto', ''),
            'fonte_url': manual.get('fonte_url', ''),
            'driver_url': manual.get('driver_url', ''),
            'driver_label': manual.get('driver_label', ''),
            'idioma': manual.get('idioma', ''),
            'status': manual.get('status', ''),
            'versao_documento': 'legado',
            'atualizado_em': '',
            'aliases': list(manual.get('aliases', [])),
            'tags': [manual.get('tipo', ''), manual.get('driver_label', '')],
        }

    @classmethod
    @lru_cache(maxsize=1)
    def _dados_catalogo(cls):
        manuais = [
            cls._manual_como_documento(item, indice)
            for indice, item in enumerate(ManualService._dados_catalogo(), start=1)
        ]
        return manuais + [dict(item) for item in cls._documentos_json()]

    @classmethod
    def limpar_cache(cls):
        cls._documentos_json.cache_clear()
        cls._dados_catalogo.cache_clear()

    @classmethod
    def _preparar_item(cls, item_original):
        item = dict(item_original)
        if item.get('tipo_documento') == 'MANUAL_OFICIAL':
            item = ManualService._localizar_item(item)
        arquivo = item.get('arquivo', '')
        arquivo_url_privado = item.get('arquivo_url', '')
        arquivo_relativo = ''
        if arquivo:
            try:
                raiz_estatica = cls.STATIC_ROOT.resolve()
                caminho_arquivo = (raiz_estatica / arquivo).resolve()
                relativo = caminho_arquivo.relative_to(raiz_estatica)
                if caminho_arquivo.is_file() and caminho_arquivo.suffix.lower() == '.pdf':
                    arquivo_relativo = relativo.as_posix()
            except (OSError, ValueError):
                arquivo_relativo = ''
        item['arquivo_disponivel'] = bool(arquivo_relativo or arquivo_url_privado)
        item['arquivo_url'] = (
            arquivo_url_privado
            or (static(arquivo_relativo) if arquivo_relativo else '')
        )
        item['tipo_label'] = _(cls.TIPOS.get(
            item.get('tipo_documento'), item.get('tipo_documento', '')
        ))
        item['revisao_interna'] = item.get('status') == 'pronto_revisao_interna'
        item['pendente'] = item.get('status') in {'identificacao_pendente', 'indisponivel'}
        return item

    @classmethod
    def _clientes_autorizados(cls, user):
        from django.db.models import Prefetch

        from insumos.models import Cliente, ClienteRelatorio, Inventario
        from insumos.utils import secure_queryset_insumos

        if user is None or not getattr(user, 'is_authenticated', False):
            return Cliente.objects.none()
        perfil = getattr(user, 'perfil', None)
        if not perfil:
            return Cliente.objects.none()
        if perfil.is_admin:
            clientes = Cliente.objects.filter(ativo=True)
        else:
            inventarios = secure_queryset_insumos(
                Inventario.objects.all(), user, campo_base='base'
            )
            clientes = Cliente.objects.filter(
                ativo=True, inventarios__in=inventarios
            ).distinct()
        relatorios = ClienteRelatorio.objects.filter(
            ativo=True,
            tipo_relatorio__ativo=True,
        ).select_related('tipo_relatorio')
        return clientes.select_related('checklist_documento').prefetch_related(
            Prefetch(
                'relatorios_requeridos',
                queryset=relatorios,
                to_attr='relatorios_documentacao',
            )
        )

    @staticmethod
    def _relatorios_do_cliente(cliente):
        return list(getattr(cliente, 'relatorios_documentacao', []))

    @classmethod
    def _checklists_cliente(cls, user):
        documentos = []
        for cliente in cls._clientes_autorizados(user):
            checklist = getattr(cliente, 'checklist_documento', None)
            relatorios = cls._relatorios_do_cliente(cliente)
            resumo_arquivo = (
                f'Arquivo disponível: {checklist.nome_original}.'
                if checklist
                else 'O arquivo de checklist ainda não foi enviado.'
            )
            resumo_relatorios = (
                ' Relatórios cadastrados: '
                + ', '.join(item.tipo_relatorio.nome for item in relatorios)
                + '.'
                if relatorios
                else ' Nenhum relatório específico foi cadastrado.'
            )
            documentos.append({
                'id': f'cliente-{cliente.pk}-checklist',
                'tipo_documento': 'CHECKLIST_CLIENTE',
                'produto_codigo': '',
                'cliente_sigla': cliente.sigla,
                'categoria': 'Clientes',
                'fabricante': '',
                'modelo': cliente.sigla,
                'titulo': f'{cliente.sigla} - Checklist de entregáveis',
                'resumo': resumo_arquivo + resumo_relatorios,
                'arquivo': '',
                'fonte_url': '',
                'detalhe_url': reverse(
                    'estoque:documentacao_cliente_detalhe', args=[cliente.pk]
                ),
                'idioma': 'Português (Brasil)',
                'status': 'disponivel' if checklist else 'indisponivel',
                'versao_documento': '',
                'atualizado_em': (
                    checklist.atualizado_em.date().isoformat() if checklist else ''
                ),
                'aliases': [cliente.sigla, cliente.nome],
                'tags': [item.tipo_relatorio.nome for item in relatorios],
            })
        return documentos

    @classmethod
    def _videos_catalogo(cls):
        from estoque.models import VideoDocumentacao

        return [{
            'id': f'video-{video.pk}',
            'tipo_documento': 'VIDEO',
            'produto_codigo': video.produto_codigo,
            'produto': '',
            'cliente_sigla': '',
            'categoria': video.categoria,
            'fabricante': '',
            'modelo': video.produto_codigo,
            'titulo': video.titulo,
            'resumo': video.descricao,
            'arquivo': '',
            'fonte_url': video.url,
            'embed_url': cls._youtube_embed_url(video.url),
            'origem': video.get_origem_display(),
            'idioma': _('Português (Brasil)'),
            'status': 'disponivel',
            'versao_documento': '',
            'atualizado_em': video.atualizado_em.date().isoformat(),
            'duracao': video.duracao,
            'publicado_em': video.publicado_em,
            'aliases': [video.titulo, video.produto_codigo],
            'tags': [tag.strip() for tag in video.tags.split(',') if tag.strip()],
            'objeto_id': video.pk,
        } for video in VideoDocumentacao.objects.filter(ativo=True)]

    @classmethod
    def _resolucoes_upload(cls):
        from estoque.models import ResolucaoDocumento

        return [{
            'id': f'resolucao-upload-{documento.pk}',
            'tipo_documento': 'RESOLUCAO',
            'produto_codigo': '',
            'produto': '',
            'cliente_sigla': '',
            'categoria': documento.categoria,
            'fabricante': documento.fabricante,
            'modelo': documento.modelo,
            'titulo': documento.titulo,
            'resumo': documento.resumo,
            'arquivo': '',
            'arquivo_url': reverse(
                'estoque:documentacao_resolucao_arquivo', args=[documento.pk]
            ),
            'fonte_url': '',
            'idioma': documento.get_idioma_display(),
            'idioma_codigo': documento.idioma,
            'status': 'disponivel',
            'versao_documento': '',
            'atualizado_em': documento.atualizado_em.date().isoformat(),
            'aliases': [
                documento.fabricante, documento.modelo, documento.titulo,
                documento.nome_original,
            ],
            'tags': [tag.strip() for tag in documento.tags.split(',') if tag.strip()],
            'objeto_id': documento.pk,
            'resolucao_upload': True,
        } for documento in ResolucaoDocumento.objects.filter(ativo=True)]

    @classmethod
    def listar(
        cls, termo='', tipo='', categoria='', fabricante='', modelo='', cliente='', idioma='',
        user=None,
    ):
        filtros = {
            'tipo_documento': tipo,
            'categoria': categoria,
            'fabricante': fabricante,
            'modelo': modelo,
            'cliente_sigla': cliente,
            'idioma': idioma,
        }
        termo_normalizado = ManualService.normalizar(termo)
        resultado = []
        catalogo = list(cls._dados_catalogo())
        catalogo.extend(cls._resolucoes_upload())
        catalogo.extend(cls._videos_catalogo())
        if user is not None:
            catalogo.extend(cls._checklists_cliente(user))
        for original in catalogo:
            item = cls._preparar_item(original)
            busca = ManualService.normalizar(' '.join([
                item.get('produto_codigo', ''), item.get('produto', ''),
                item.get('fabricante', ''), item.get('modelo', ''),
                item.get('titulo', ''), item.get('resumo', ''),
                item.get('idioma', ''), item.get('driver_label', ''),
                ' '.join(item.get('aliases', [])), ' '.join(item.get('tags', [])),
            ]))
            if termo_normalizado and not all(token in busca for token in termo_normalizado.split()):
                continue
            descartado = False
            for campo, valor in filtros.items():
                valor_normalizado = ManualService.normalizar(valor)
                if campo == 'idioma' and valor_normalizado:
                    idioma_codigo = ManualService.normalizar(
                        item.get('idioma_codigo', '')
                    )
                    idioma_label = ManualService.normalizar(item.get('idioma', ''))
                    corresponde = (
                        idioma_codigo == valor_normalizado
                        or (
                            valor_normalizado == 'es'
                            and idioma_label in {'espanhol', 'espanol', 'spanish'}
                        )
                        or (
                            valor_normalizado == 'pt br'
                            and idioma_label.startswith('portugues')
                        )
                    )
                    if not corresponde:
                        descartado = True
                        break
                elif valor_normalizado and valor_normalizado not in ManualService.normalizar(item.get(campo, '')):
                    descartado = True
                    break
            if not descartado:
                resultado.append(item)
        return sorted(
            resultado,
            key=lambda item: (
                item['pendente'],
                item.get('tipo_documento') != 'RESOLUCAO',
                item.get('categoria', ''),
                item.get('modelo', ''),
            ),
        )

    @classmethod
    def estatisticas(cls, itens=None):
        itens = list(itens if itens is not None else cls.listar())
        return {
            'total': len(itens),
            'manuais': sum(item.get('tipo_documento') == 'MANUAL_OFICIAL' for item in itens),
            'resolucoes': sum(item.get('tipo_documento') == 'RESOLUCAO' for item in itens),
            'checklists': sum(item.get('tipo_documento') == 'CHECKLIST_CLIENTE' for item in itens),
            'videos': sum(item.get('tipo_documento') == 'VIDEO' for item in itens),
        }

    @classmethod
    def para_produto(cls, produto):
        """Retorna documentos pelo vínculo explícito do produto, sem usar texto do chamado."""
        codigo = str(getattr(produto, 'codigo', '') or '').strip()
        if not codigo:
            return []
        catalogo = (
            list(cls._dados_catalogo())
            + cls._resolucoes_upload()
            + cls._videos_catalogo()
        )
        documentos = [
            cls._preparar_item(item)
            for item in catalogo
            if str(item.get('produto_codigo', '')).strip() == codigo
        ]
        ordem = {'RESOLUCAO': 0, 'MANUAL_OFICIAL': 1, 'DRIVER_FIRMWARE': 2, 'VIDEO': 3}
        return sorted(
            documentos,
            key=lambda item: (ordem.get(item.get('tipo_documento'), 9), item.get('titulo', '')),
        )

    @classmethod
    def _item_da_pergunta(cls, pergunta, tipo_preferido=''):
        texto = ManualService.normalizar(pergunta)
        candidatos = []
        for item in list(cls._dados_catalogo()) + cls._resolucoes_upload():
            if tipo_preferido and item.get('tipo_documento') != tipo_preferido:
                continue
            melhor_alias = 0
            for alias in item.get('aliases', []):
                alias_normalizado = ManualService.normalizar(alias)
                if len(alias_normalizado) >= 4 and re.search(
                    rf'(^|\s){re.escape(alias_normalizado)}(\s|$)', texto
                ):
                    melhor_alias = max(melhor_alias, len(alias_normalizado))
            if melhor_alias:
                candidatos.append((melhor_alias, item))
        return max(candidatos, key=lambda candidato: candidato[0])[1] if candidatos else None

    @classmethod
    def _responder_checklist_cliente(cls, pergunta, user):
        url = reverse('estoque:documentacao_clientes')
        if user is None or not getattr(user, 'is_authenticated', False):
            return None
        clientes = cls._clientes_autorizados(user)
        texto = ManualService.normalizar(pergunta)
        alias_solicitado = next(
            (sigla for alias, sigla in cls.CLIENTE_ALIASES.items() if alias in texto),
            '',
        )
        cliente = None
        for candidato in clientes:
            sigla = ManualService.normalizar(candidato.sigla)
            nome = ManualService.normalizar(candidato.nome)
            if (
                (sigla and re.search(rf'(^|\s){re.escape(sigla)}(\s|$)', texto))
                or (nome and nome in texto)
                or (alias_solicitado and sigla == alias_solicitado)
            ):
                cliente = candidato
                break
        if not cliente:
            return {
                'resposta': 'Informe a sigla ou o nome do cliente para consultar os entregáveis disponíveis no seu escopo.',
                'tipo': 'texto',
                'acoes': [{'label': 'Abrir checklist de clientes', 'url': url}],
                'interpretacao': {'intencao': 'documentacao_clientes'},
                'contexto': {'intencao': 'documentacao_clientes', 'tipo_documento': 'CHECKLIST_CLIENTE'},
            }
        checklist = getattr(cliente, 'checklist_documento', None)
        relatorios = cls._relatorios_do_cliente(cliente)
        trecho_relatorios = (
            ' Os relatórios cadastrados são: '
            + '; '.join(
                f'{item.tipo_relatorio.nome}'
                + (' (obrigatório)' if item.obrigatorio else ' (opcional)')
                for item in relatorios
            )
            + '.'
            if relatorios
            else ' Não há relatórios específicos cadastrados para esse cliente.'
        )
        trecho_arquivo = (
            f'O checklist do cliente {cliente.sigla} está disponível no arquivo '
            f'{checklist.nome_original}.'
            if checklist
            else f'O arquivo de checklist do cliente {cliente.sigla} ainda não foi enviado.'
        )
        resposta = trecho_arquivo + trecho_relatorios
        return {
            'resposta': resposta,
            'tipo': 'texto',
            'acoes': [{
                'label': 'Ver checklist do cliente',
                'url': reverse('estoque:documentacao_cliente_detalhe', args=[cliente.pk]),
            }],
            'interpretacao': {'intencao': 'documentacao_clientes', 'cliente': cliente.sigla},
            'contexto': {
                'intencao': 'documentacao_clientes',
                'tipo_documento': 'CHECKLIST_CLIENTE',
                'cliente_id': cliente.pk,
            },
        }

    @classmethod
    def tentar_responder(cls, pergunta, user=None):
        texto = ManualService.normalizar(pergunta)
        if any(ManualService.normalizar(valor) in texto for valor in cls.MARCADORES_CHECKLIST):
            return cls._responder_checklist_cliente(pergunta, user)
        consulta_operacional = bool(
            re.search(r'\b(equipamento|equipamentos|patrimonio|patrimonios|serial|serie)\b', texto)
            and re.search(r'\b(status|situacao|etapa|sick|manutencao|transferencia|emprestimo)\b', texto)
            and not re.search(
                r'\b(manual|manuais|guia|instrucoes|documentacao|como|configurar|instalar|'
                r'trocar|limpar|resetar|reiniciar|driver|firmware|problema|resolver)\b',
                texto,
            )
        )
        if consulta_operacional:
            return None

        pede_driver = any(ManualService.normalizar(valor) in texto for valor in ManualService.MARCADORES_DRIVER)
        pede_manual = bool(re.search(r'\b(manual|manuais|guia oficial)\b', texto))
        pede_resolucao = not pede_manual and any(
            ManualService.normalizar(valor) in texto for valor in cls.MARCADORES_RESOLUCAO
        )
        tem_marcador = (
            pede_driver or pede_manual or pede_resolucao
            or any(ManualService.normalizar(valor) in texto for valor in ManualService.MARCADORES)
            or 'documentacao' in texto
        )
        tipo_preferido = 'MANUAL_OFICIAL' if (pede_manual or pede_driver) else ('RESOLUCAO' if pede_resolucao else '')
        item = cls._item_da_pergunta(pergunta, tipo_preferido)
        if not item and tipo_preferido:
            item = cls._item_da_pergunta(pergunta)
        if not tem_marcador and not item:
            return None

        central_url = reverse('estoque:documentacao')
        if not item:
            if pede_resolucao:
                assunto, intencao, url = 'procedimentos internos de resolução', 'documentacao_resolucao', reverse('estoque:documentacao_resolucao')
            elif pede_driver:
                assunto, intencao, url = 'drivers, firmwares e softwares oficiais', 'drivers', reverse('estoque:manuais')
            else:
                assunto, intencao, url = 'documentos e manuais cadastrados', 'manuais', central_url
            return {
                'resposta': f'Posso consultar {assunto}. Informe o fabricante ou o modelo do equipamento, por exemplo: “código 43 na Xerox 3020” ou “manual do TL-WR829N”.',
                'tipo': 'texto',
                'acoes': [{'label': 'Pesquisar na Central de Documentação', 'url': url}],
                'interpretacao': {'intencao': intencao},
                'contexto': {'intencao': intencao},
            }

        item = cls._preparar_item(item)
        if pede_driver and item.get('driver_url'):
            return {
                'resposta': f"Encontrei o acesso oficial de drivers e software para {item.get('produto') or item['modelo']}. Confirme o sistema operacional e a revisão do hardware antes de instalar.",
                'tipo': 'texto',
                'acoes': [
                    {'label': item.get('driver_label') or 'Abrir drivers oficiais', 'url': item['driver_url']},
                    {'label': 'Ver na biblioteca de manuais', 'url': f"{reverse('estoque:manuais')}?q={quote_plus(item['modelo'])}"},
                ],
                'interpretacao': {'intencao': 'drivers', 'modelo': item.get('modelo', '')},
                'contexto': {'intencao': 'drivers', 'produto_codigo': item.get('produto_codigo', ''), 'tipo_documento': 'MANUAL_OFICIAL'},
            }

        if item.get('status') == 'identificacao_pendente':
            return {
                'resposta': f"Ainda não é seguro indicar um documento para {item.get('produto') or item['modelo']}: {item['resumo']}",
                'tipo': 'texto',
                'acoes': [{'label': 'Ver pendência na Central', 'url': f"{central_url}?q={quote_plus(item['modelo'])}"}],
                'interpretacao': {'intencao': 'manuais', 'modelo': item.get('modelo', '')},
                'contexto': {'intencao': 'manuais', 'produto_codigo': item.get('produto_codigo', '')},
            }

        tipo_documento = item.get('tipo_documento')
        if tipo_documento == 'RESOLUCAO':
            intencao = 'documentacao_resolucao'
            resposta = f"Encontrei um procedimento interno para {item['modelo']}: {item['resumo']}"
            pagina_url = f"{reverse('estoque:documentacao_resolucao')}?q={quote_plus(item['modelo'])}"
            label_pagina = 'Ver em resolução de problemas'
        else:
            intencao = 'manuais'
            trecho = ManualService._trecho_relevante(item, pergunta)
            resposta = (
                f"Conforme o manual oficial {item['titulo']} ({item['idioma']}): {trecho}"
                if trecho else f"Encontrei o manual oficial {item['titulo']}. {item['resumo']}"
            )
            pagina_url = f"{reverse('estoque:manuais')}?q={quote_plus(item['modelo'])}"
            label_pagina = 'Ver na biblioteca de manuais'
        acoes = [{'label': label_pagina, 'url': pagina_url}]
        if item['arquivo_disponivel']:
            acoes.insert(0, {
                'label': 'Abrir procedimento' if tipo_documento == 'RESOLUCAO' else 'Abrir manual',
                'url': item['arquivo_url'],
            })
        return {
            'resposta': resposta,
            'tipo': 'texto',
            'acoes': acoes,
            'interpretacao': {'intencao': intencao, 'modelo': item.get('modelo', '')},
            'contexto': {
                'intencao': intencao,
                'produto_codigo': item.get('produto_codigo', ''),
                'tipo_documento': tipo_documento,
                'documento_id': item.get('id', ''),
            },
        }
