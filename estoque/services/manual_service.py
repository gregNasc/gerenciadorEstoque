import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from estoque.models import Equipamento


# O catálogo é JSON, portanto estes marcadores permitem que o makemessages
# inclua também o conteúdo exibido nos cartões de manuais.
CATALOG_TRANSLATABLE_STRINGS = (
    gettext_noop('COLETOR DE DADOS MOTOROLA MC-65'),
    gettext_noop('COLETOR DE DADOS MOBYDATA'),
    gettext_noop('COLETOR DE DADOS MOVFAST RANGER 2K'),
    gettext_noop('COLETOR DE DADOS MOVFAST AR-T8'),
    gettext_noop('IMPRESSORA HP LASER'),
    gettext_noop('IMPRESSORA SAMSUNG M2020'),
    gettext_noop('IMPRESSORA XEROX 3020'),
    gettext_noop('NOTEBOOK DELL VOSTRO 15 3510'),
    gettext_noop('ROUTER TP-LINK TL-WR829N'),
    gettext_noop('COLETOR DE DADOS SKORPIO X3'),
    gettext_noop('COLETOR DE DADOS SKORPIO X4'),
    gettext_noop('IMPRESSORA PANTUM P2500W'),
    gettext_noop('NOTEBOOK DELL INSPIRON 3000'),
    gettext_noop('NOTEBOOK DELL INSPIRON 5000'),
    gettext_noop('NOTEBOOK LG'),
    gettext_noop('NOTEBOOK SAMSUNG'),
    gettext_noop('NOTEBOOK LENOVO IDEALPAD 1'),
    gettext_noop('NOTEBOOK DELL INSPIRON 3520'),
    gettext_noop('NOTEBOOK COMPAC'),
    gettext_noop('ROUTER MIKROTIK AC'),
    gettext_noop('ROUTER MIKROTIK AC LITE'),
    gettext_noop('COLETOR DE DADOS UROVO DT-40'),
    gettext_noop('Não informado no cadastro'),
    gettext_noop('Série Inspiron 3000'),
    gettext_noop('Série Inspiron 5000'),
    gettext_noop('IdeaPad 1 (submodelo não informado)'),
    gettext_noop('AC (modelo completo não informado)'),
    gettext_noop('Coletores'),
    gettext_noop('Impressoras'),
    gettext_noop('Notebooks'),
    gettext_noop('Routers'),
    gettext_noop('Guia de inicialização rápida MC65'),
    gettext_noop('Identificação do modelo necessária'),
    gettext_noop('Guia rápido Ranger 2K(N)'),
    gettext_noop('Página técnica AR-T8'),
    gettext_noop('Guia de referência HP Laser série 100'),
    gettext_noop('Central oficial SL-M2020'),
    gettext_noop('Guia do usuário Phaser 3020'),
    gettext_noop('Manuais e documentos Vostro 15 3510'),
    gettext_noop('Guia de instalação rápida TL-WR829N'),
    gettext_noop('Guia rápido Skorpio X3'),
    gettext_noop('Documentação técnica Skorpio X4'),
    gettext_noop('Guia do usuário Pantum P2200/P2500 Series V2.0'),
    gettext_noop('Identificação do submodelo necessária'),
    gettext_noop('Manuais e documentos Inspiron 15 3520'),
    gettext_noop('Guia hAP ac lite'),
    gettext_noop('Página oficial Urovo DT40'),
    gettext_noop('Guia de inicialização rápida'),
    gettext_noop('Cadastro pendente'),
    gettext_noop('Guia rápido'),
    gettext_noop('Ficha técnica do fornecedor'),
    gettext_noop('Guia de referência'),
    gettext_noop('Manual e suporte'),
    gettext_noop('Guia do usuário'),
    gettext_noop('Instalação, especificações e serviço'),
    gettext_noop('Guia de instalação'),
    gettext_noop('Manual e guia rápido'),
    gettext_noop('Manual do usuário'),
    gettext_noop('Especificações e orientação'),
    gettext_noop('Português'),
    gettext_noop('Português (Brasil)'),
    gettext_noop('Português / Inglês'),
    gettext_noop('Português (Portugal)'),
    gettext_noop('Vários idiomas'),
    gettext_noop('Inglês'),
    gettext_noop('Software e downloads oficiais'),
    gettext_noop('Solicitar software oficial'),
    gettext_noop('Suporte de software do fornecedor'),
    gettext_noop('Drivers e firmware oficiais'),
    gettext_noop('Drivers oficiais'),
    gettext_noop('Drivers e BIOS oficiais'),
    gettext_noop('Firmware oficial'),
    gettext_noop('Software e firmware oficiais'),
    gettext_noop('Identificar modelo e baixar drivers'),
    gettext_noop('Identificar modelo e baixar software'),
    gettext_noop('Identificar submodelo e baixar drivers'),
    gettext_noop('RouterOS, WinBox e firmware oficiais'),
    gettext_noop('Software e ferramentas oficiais'),
    gettext_noop('Guia em português do computador móvel MC65, com teclas e componentes, bateria, carregamento, SIM e microSD, comunicação, acessórios e captura de dados.'),
    gettext_noop('O cadastro não informa o modelo MobyData. Confirme o código da etiqueta para associar o manual correto.'),
    gettext_noop('Guia oficial em português com segurança, bateria, identificação dos componentes, carregamento e uso inicial.'),
    gettext_noop('Informações técnicas publicadas pelo fornecedor. Não foi localizado um manual público oficial para download.'),
    gettext_noop('Guia oficial em português da família HP Laser 100, que abrange os modelos 103, 107 e 108, com instalação, conexão sem fio, toner e solução de problemas.'),
    gettext_noop('Central oficial para localizar o manual da impressora Samsung SL-M2020.'),
    gettext_noop('Manual oficial em português com instalação, Wi-Fi, impressão, manutenção, suprimentos e solução de problemas.'),
    gettext_noop('Documentação oficial em português com configuração, especificações, diagnóstico e manutenção.'),
    gettext_noop('Guia oficial em português com instalação, modos de operação, acesso, senha, Wi-Fi, reset e perguntas frequentes.'),
    gettext_noop('Guia oficial em português com conteúdo da embalagem, bateria, carregamento, teclas e uso inicial.'),
    gettext_noop('Central oficial com guia rápido em português e manual completo em inglês para o Skorpio X4.'),
    gettext_noop('Guia do usuário V2.0 em português para as séries Pantum P2200/P2200W, P2500/P2500W, S2000 e P2600, com instalação, Wi-Fi, papel, toner, manutenção e solução de problemas.'),
    gettext_noop('Inspiron 3000 é uma família. Use o modelo completo ou a etiqueta de serviço para localizar o manual correto.'),
    gettext_noop('Inspiron 5000 é uma família. Use o modelo completo ou a etiqueta de serviço para localizar o manual correto.'),
    gettext_noop('O cadastro informa apenas o fabricante. Confirme o modelo completo na etiqueta inferior.'),
    gettext_noop('O cadastro informa apenas o fabricante. Confirme o código completo do modelo para associar o manual.'),
    gettext_noop('IdeaPad 1 possui submodelos diferentes. Confirme o código como 14/15 e a variante impressa na etiqueta.'),
    gettext_noop('Documentação oficial em português com configuração, especificações e manutenção do Inspiron 15 3520.'),
    gettext_noop('O cadastro não informa o modelo e usa a grafia “Compac”. Confirme fabricante e modelo na etiqueta.'),
    gettext_noop('AC não identifica o hardware MikroTik. Confirme o código RB da etiqueta antes de usar instruções de energia ou reset.'),
    gettext_noop('Guia oficial com instalação, alimentação, acesso inicial, atualização, senha, Wi-Fi e reset.'),
    gettext_noop('Página oficial com operação, acessórios, conectividade, bateria, proteção e especificações do DT40.'),
)


class ManualService:
    CATALOGO = Path(__file__).resolve().parent.parent / 'data' / 'manuais.json'
    STATIC_ROOT = Path(settings.BASE_DIR) / 'estoque' / 'static'
    MARCADORES_DRIVER = (
        'driver', 'drivers', 'firmware', 'software', 'bios', 'winbox',
        'routeros', 'atualizacao do sistema', 'atualizar o sistema',
        'controlador', 'controladores', 'actualizacion del sistema',
        'actualizar el sistema',
    )
    MARCADORES = (
        'manual', 'manuais', 'guia', 'instrucoes', 'instrucao', 'documentacao',
        'configuracao', 'instalacao', 'manutencao',
        'como configurar', 'como instalar', 'como trocar', 'como limpar',
        'como resetar', 'como reiniciar', 'como carregar', 'como conectar',
        'senha', 'bateria', 'toner', 'wifi', 'wi-fi', 'reset',
        'manuales', 'guia', 'instrucciones', 'documentacion', 'configuracion',
        'instalacion', 'mantenimiento', 'como configurar', 'como instalar',
        'como cambiar', 'como limpiar', 'como reiniciar', 'contraseña',
    ) + MARCADORES_DRIVER
    STOPWORDS = {
        'a', 'ao', 'as', 'como', 'da', 'de', 'do', 'e', 'em', 'eu', 'manual',
        'me', 'o', 'os', 'para', 'por', 'qual', 'que', 'um', 'uma', 'no', 'na',
        'el', 'la', 'los', 'las', 'un', 'una', 'del', 'en', 'y', 'para', 'por',
    }
    CAMPOS_TRADUZIVEIS = (
        'produto', 'modelo', 'categoria', 'titulo', 'tipo', 'idioma',
        'resumo', 'driver_label',
    )

    @staticmethod
    def normalizar(valor):
        texto = unicodedata.normalize('NFKD', str(valor or ''))
        texto = ''.join(ch for ch in texto if not unicodedata.combining(ch))
        return re.sub(r'[^a-z0-9]+', ' ', texto.lower()).strip()

    @classmethod
    @lru_cache(maxsize=1)
    def _dados_catalogo(cls):
        with cls.CATALOGO.open(encoding='utf-8') as arquivo:
            return json.load(arquivo)['manuais']

    @classmethod
    def _localizar_item(cls, item_original):
        item = dict(item_original)
        for campo in cls.CAMPOS_TRADUZIVEIS:
            if item.get(campo):
                item[campo] = _(item[campo])
        return item

    @classmethod
    def listar(cls, termo='', categoria='', idioma=''):
        codigos_com_estoque = set(
            Equipamento.objects.filter(produto__isnull=False)
            .values_list('produto__codigo', flat=True)
            .distinct()
        )
        termo_normalizado = cls.normalizar(termo)
        categoria_normalizada = cls.normalizar(categoria)
        idioma_normalizado = cls.normalizar(idioma)
        resultado = []

        for item_original in cls._dados_catalogo():
            if item_original['produto_codigo'] not in codigos_com_estoque:
                continue
            item = cls._localizar_item(item_original)
            busca = cls.normalizar(' '.join([
                item.get('produto', ''), item.get('fabricante', ''),
                item.get('modelo', ''), item.get('titulo', ''),
                item.get('tipo', ''), item.get('idioma', ''),
                item.get('resumo', ''), item.get('driver_label', ''),
                ' '.join(item.get('aliases', [])),
            ]))
            if termo_normalizado and not all(token in busca for token in termo_normalizado.split()):
                continue
            if categoria_normalizada and cls.normalizar(item.get('categoria')) != categoria_normalizada:
                continue
            if idioma_normalizado and idioma_normalizado not in cls.normalizar(item.get('idioma')):
                continue

            arquivo = item.get('arquivo', '')
            item['arquivo_disponivel'] = bool(arquivo and (cls.STATIC_ROOT / arquivo).is_file())
            item['arquivo_url'] = static(arquivo) if item['arquivo_disponivel'] else ''
            item['pendente'] = item.get('status') == 'identificacao_pendente'
            resultado.append(item)

        return sorted(
            resultado,
            key=lambda item: (item['pendente'], item.get('categoria', ''), item.get('produto', '')),
        )

    @classmethod
    def estatisticas(cls, itens):
        return {
            'total': len(itens),
            'pt_br': sum('portugues' in cls.normalizar(item.get('idioma')) for item in itens),
            'locais': sum(bool(item.get('arquivo_disponivel')) for item in itens),
            'pendentes': sum(bool(item.get('pendente')) for item in itens),
        }

    @classmethod
    def _item_da_pergunta(cls, pergunta):
        texto = cls.normalizar(pergunta)
        candidatos = []
        for item in cls._dados_catalogo():
            for alias in item.get('aliases', []):
                alias_normalizado = cls.normalizar(alias)
                if len(alias_normalizado) >= 4 and re.search(
                    rf'(^|\s){re.escape(alias_normalizado)}(\s|$)', texto
                ):
                    candidatos.append((len(alias_normalizado), item))
        return max(candidatos, key=lambda candidato: candidato[0])[1] if candidatos else None

    @classmethod
    def _trecho_relevante(cls, item, pergunta):
        caminho = item.get('texto')
        if not caminho:
            return ''
        arquivo = cls.STATIC_ROOT / caminho
        if not arquivo.is_file():
            return ''
        termos = {
            token for token in cls.normalizar(pergunta).split()
            if len(token) > 2 and token not in cls.STOPWORDS
        }
        if not termos:
            return ''
        conteudo = arquivo.read_text(encoding='utf-8', errors='ignore')
        blocos = [re.sub(r'\s+', ' ', bloco).strip() for bloco in re.split(r'\n\s*\n', conteudo)]
        pontuados = []
        for bloco in blocos:
            if len(bloco) < 45:
                continue
            normalizado = cls.normalizar(bloco)
            pontos = sum(2 if termo in normalizado else 0 for termo in termos)
            if pontos:
                pontuados.append((pontos, min(len(bloco), 700), bloco))
        if not pontuados:
            return ''
        trecho = max(pontuados, key=lambda valor: (valor[0], -valor[1]))[2]
        return trecho[:600].rsplit(' ', 1)[0] + ('…' if len(trecho) > 600 else '')

    @classmethod
    def tentar_responder(cls, pergunta):
        texto = cls.normalizar(pergunta)
        consulta_operacional = bool(
            re.search(r'\b(equipamento|equipamentos|patrimonio|patrimonios|serial|serie)\b', texto)
            and re.search(r'\b(status|situacao|etapa|sick|manutencao|transferencia|emprestimo)\b', texto)
            and not re.search(
                r'\b(manual|manuais|guia|instrucoes|documentacao|como|configurar|instalar|'
                r'trocar|limpar|resetar|reiniciar|driver|firmware)\b',
                texto,
            )
        )
        if consulta_operacional:
            return None
        item = cls._item_da_pergunta(pergunta)
        if item:
            item = cls._localizar_item(item)
        pede_driver = any(cls.normalizar(marcador) in texto for marcador in cls.MARCADORES_DRIVER)
        tem_marcador = any(cls.normalizar(marcador) in texto for marcador in cls.MARCADORES)
        if not tem_marcador and not item:
            return None
        if item and not tem_marcador:
            verbos_ajuda = (
                'configurar', 'configuracao', 'instalar', 'instalacao', 'limpar',
                'limpeza', 'trocar', 'resetar', 'reiniciar', 'carregar', 'conectar',
                'manutencao',
            )
            if not any(verbo in texto for verbo in verbos_ajuda):
                return None

        biblioteca_url = reverse('estoque:manuais')
        if not item:
            assunto = (
                _('drivers, firmwares e softwares oficiais')
                if pede_driver else _('manuais cadastrados')
            )
            intencao = 'drivers' if pede_driver else 'manuais'
            return {
                'resposta': _(
                    'Posso consultar %(assunto)s. Informe o fabricante ou o modelo '
                    'do equipamento, por exemplo: “driver da HP Laser 107” ou '
                    '“manual do TL-WR829N”.'
                ) % {'assunto': assunto},
                'tipo': 'texto',
                'acoes': [{
                    'label': _('Pesquisar na biblioteca de manuais'),
                    'url': biblioteca_url,
                }],
                'interpretacao': {'intencao': intencao},
                'contexto': {'intencao': intencao},
            }

        if pede_driver and item.get('driver_url'):
            pendencia = item.get('status') == 'identificacao_pendente'
            if pendencia:
                resposta = _(
                    'O cadastro de %(produto)s ainda não informa o modelo completo. '
                    'Abra o portal oficial abaixo e identifique o equipamento pela '
                    'etiqueta ou número de série antes de instalar qualquer driver.'
                ) % {'produto': item['produto']}
            else:
                resposta = _(
                    'Encontrei o acesso oficial de drivers e software para '
                    '%(produto)s. Confirme o sistema operacional, a versão e a '
                    'revisão do hardware antes de baixar ou atualizar.'
                ) % {'produto': item['produto']}
            return {
                'resposta': resposta,
                'tipo': 'texto',
                'acoes': [
                    {'label': item.get('driver_label', _('Abrir drivers oficiais')), 'url': item['driver_url']},
                    {'label': _('Ver na biblioteca de manuais'), 'url': f"{biblioteca_url}?q={quote_plus(item['modelo'])}"},
                ],
                'interpretacao': {'intencao': 'drivers', 'modelo': item.get('modelo', '')},
                'contexto': {'intencao': 'drivers', 'produto_codigo': item['produto_codigo']},
            }

        if item.get('status') == 'identificacao_pendente':
            return {
                'resposta': _(
                    'Ainda não é seguro indicar um manual para %(produto)s: %(resumo)s'
                ) % {'produto': item['produto'], 'resumo': item['resumo']},
                'tipo': 'texto',
                'acoes': [{
                    'label': _('Ver pendência na biblioteca'),
                    'url': f"{biblioteca_url}?q={quote_plus(item['produto'])}",
                }],
                'interpretacao': {'intencao': 'manuais', 'modelo': item.get('modelo', '')},
                'contexto': {'intencao': 'manuais', 'produto_codigo': item['produto_codigo']},
            }

        trecho = cls._trecho_relevante(item, pergunta)
        if trecho:
            resposta = _('%(titulo)s (%(idioma)s) informa: %(trecho)s') % {
                'titulo': item['titulo'],
                'idioma': item['idioma'],
                'trecho': trecho,
            }
        else:
            resposta = _(
                'Encontrei %(titulo)s para %(produto)s. %(resumo)s'
            ) % {
                'titulo': item['titulo'],
                'produto': item['produto'],
                'resumo': item['resumo'],
            }
        acoes = [{
            'label': _('Ver na biblioteca de manuais'),
            'url': f"{biblioteca_url}?q={quote_plus(item['modelo'])}",
        }]
        if item.get('arquivo') and (cls.STATIC_ROOT / item['arquivo']).is_file():
            acoes.insert(0, {'label': _('Abrir manual'), 'url': static(item['arquivo'])})
        return {
            'resposta': resposta,
            'tipo': 'texto',
            'acoes': acoes,
            'interpretacao': {'intencao': 'manuais', 'modelo': item.get('modelo', '')},
            'contexto': {'intencao': 'manuais', 'produto_codigo': item['produto_codigo']},
        }
