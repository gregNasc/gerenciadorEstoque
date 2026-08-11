import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

from estoque.models import Equipamento


class ManualService:
    CATALOGO = Path(__file__).resolve().parent.parent / 'data' / 'manuais.json'
    STATIC_ROOT = Path(settings.BASE_DIR) / 'estoque' / 'static'
    MARCADORES_DRIVER = (
        'driver', 'drivers', 'firmware', 'software', 'bios', 'winbox',
        'routeros', 'atualizacao do sistema', 'atualizar o sistema',
    )
    MARCADORES = (
        'manual', 'manuais', 'guia', 'instrucoes', 'instrucao', 'documentacao',
        'configuracao', 'instalacao', 'manutencao',
        'como configurar', 'como instalar', 'como trocar', 'como limpar',
        'como resetar', 'como reiniciar', 'como carregar', 'como conectar',
        'senha', 'bateria', 'toner', 'wifi', 'wi-fi', 'reset',
    ) + MARCADORES_DRIVER
    STOPWORDS = {
        'a', 'ao', 'as', 'como', 'da', 'de', 'do', 'e', 'em', 'eu', 'manual',
        'me', 'o', 'os', 'para', 'por', 'qual', 'que', 'um', 'uma', 'no', 'na',
    }

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
            item = dict(item_original)
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
            assunto = 'drivers, firmwares e softwares oficiais' if pede_driver else 'manuais cadastrados'
            intencao = 'drivers' if pede_driver else 'manuais'
            return {
                'resposta': f'Posso consultar {assunto}. Informe o fabricante ou o modelo do equipamento, por exemplo: “driver da HP Laser 107” ou “manual do TL-WR829N”.',
                'tipo': 'texto',
                'acoes': [{'label': 'Pesquisar na biblioteca de manuais', 'url': biblioteca_url}],
                'interpretacao': {'intencao': intencao},
                'contexto': {'intencao': intencao},
            }

        if pede_driver and item.get('driver_url'):
            pendencia = item.get('status') == 'identificacao_pendente'
            if pendencia:
                resposta = (
                    f"O cadastro de {item['produto']} ainda não informa o modelo completo. "
                    "Abra o portal oficial abaixo e identifique o equipamento pela etiqueta ou número de série antes de instalar qualquer driver."
                )
            else:
                resposta = (
                    f"Encontrei o acesso oficial de drivers e software para {item['produto']}. "
                    "Confirme o sistema operacional, a versão e a revisão do hardware antes de baixar ou atualizar."
                )
            return {
                'resposta': resposta,
                'tipo': 'texto',
                'acoes': [
                    {'label': item.get('driver_label', 'Abrir drivers oficiais'), 'url': item['driver_url']},
                    {'label': 'Ver na biblioteca de manuais', 'url': f"{biblioteca_url}?q={quote_plus(item['modelo'])}"},
                ],
                'interpretacao': {'intencao': 'drivers', 'modelo': item.get('modelo', '')},
                'contexto': {'intencao': 'drivers', 'produto_codigo': item['produto_codigo']},
            }

        if item.get('status') == 'identificacao_pendente':
            return {
                'resposta': f"Ainda não é seguro indicar um manual para {item['produto']}: {item['resumo']}",
                'tipo': 'texto',
                'acoes': [{
                    'label': 'Ver pendência na biblioteca',
                    'url': f"{biblioteca_url}?q={quote_plus(item['produto'])}",
                }],
                'interpretacao': {'intencao': 'manuais', 'modelo': item.get('modelo', '')},
                'contexto': {'intencao': 'manuais', 'produto_codigo': item['produto_codigo']},
            }

        trecho = cls._trecho_relevante(item, pergunta)
        if trecho:
            resposta = f"Conforme {item['titulo']} ({item['idioma']}): {trecho}"
        else:
            resposta = f"Encontrei {item['titulo']} para {item['produto']}. {item['resumo']}"
        acoes = [{
            'label': 'Ver na biblioteca de manuais',
            'url': f"{biblioteca_url}?q={quote_plus(item['modelo'])}",
        }]
        if item.get('arquivo') and (cls.STATIC_ROOT / item['arquivo']).is_file():
            acoes.insert(0, {'label': 'Abrir manual', 'url': static(item['arquivo'])})
        return {
            'resposta': resposta,
            'tipo': 'texto',
            'acoes': acoes,
            'interpretacao': {'intencao': 'manuais', 'modelo': item.get('modelo', '')},
            'contexto': {'intencao': 'manuais', 'produto_codigo': item['produto_codigo']},
        }
