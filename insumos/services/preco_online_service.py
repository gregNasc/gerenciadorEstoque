import json
import os
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction

from insumos.models import OfertaPrecoOnline, PesquisaPrecoOnline


class PrecoOnlineErro(Exception):
    pass


class _ColetorLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ancoras = []
        self._href = None
        self._texto = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a' and self._href is None:
            self._href = dict(attrs).get('href', '')
            self._texto = []

    def handle_data(self, data):
        if self._href is not None:
            self._texto.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self._href is not None:
            texto = ' '.join(' '.join(self._texto).split())
            self.ancoras.append((self._href, texto))
            self._href = None
            self._texto = []


def _decimal_brasileiro(texto):
    correspondencia = re.search(
        r'R\$\s*((?:\d{1,3}(?:\.\d{3})+|\d+)(?:[,.]\d{2}))',
        texto or '',
        flags=re.IGNORECASE,
    )
    if not correspondencia:
        return None
    numero = correspondencia.group(1)
    if ',' in numero:
        numero = numero.replace('.', '').replace(',', '.')
    try:
        return Decimal(numero)
    except InvalidOperation:
        return None


class CatalogoHtmlProvider:
    FLAG_CONFIGURACAO = ''
    NOME = ''
    ROTULO = ''
    URL_BASE = ''

    @classmethod
    def configurado(cls):
        return bool(getattr(settings, cls.FLAG_CONFIGURACAO, False))

    @classmethod
    def _url_busca(cls, termo):
        raise NotImplementedError

    @classmethod
    def _extrair_ofertas(cls, html, limite):
        raise NotImplementedError

    @classmethod
    def buscar(cls, termo, limite=20):
        if not cls.configurado():
            raise PrecoOnlineErro(
                f'A pesquisa na {cls.ROTULO} ainda não está habilitada no ambiente.'
            )
        requisicao = Request(
            cls._url_busca(termo),
            headers={
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'pt-BR,pt;q=0.9',
                'User-Agent': 'GerenciadorEstoque/1.0 (pesquisa manual de precos)',
            },
        )
        try:
            with urlopen(
                requisicao,
                timeout=getattr(settings, 'ONLINE_PRICE_SEARCH_TIMEOUT', 15),
            ) as resposta:
                charset = resposta.headers.get_content_charset() or 'utf-8'
                html = resposta.read().decode(charset, errors='replace')
        except HTTPError as erro:
            raise PrecoOnlineErro(
                f'A {cls.ROTULO} respondeu com erro HTTP {erro.code}.'
            ) from erro
        except (URLError, TimeoutError, OSError) as erro:
            raise PrecoOnlineErro(
                f'Não foi possível consultar a {cls.ROTULO} neste momento.'
            ) from erro
        return cls._extrair_ofertas(html, max(1, min(int(limite), 50)))

    @classmethod
    def _ancoras_por_url(cls, html):
        coletor = _ColetorLinks()
        coletor.feed(html)
        agrupadas = defaultdict(list)
        for href, texto in coletor.ancoras:
            url = urljoin(cls.URL_BASE, href)
            if cls._url_produto_valida(url):
                agrupadas[url].append(texto)
        return agrupadas

    @classmethod
    def _oferta(cls, *, codigo, titulo, url, preco):
        return {
            'fonte': cls.NOME,
            'codigo_externo': str(codigo)[:80],
            'titulo': titulo[:255],
            'vendedor': cls.ROTULO[:160],
            'url': url,
            'preco': preco,
            'frete': None,
            'preco_total': preco,
            'frete_conhecido': False,
            'condicao': 'novo',
        }


class GimbaProvider(CatalogoHtmlProvider):
    FLAG_CONFIGURACAO = 'GIMBA_PRICE_SEARCH_ENABLED'
    NOME = 'GIMBA'
    ROTULO = 'Gimba'
    URL_BASE = 'https://www.gimba.com.br/'

    @classmethod
    def _url_busca(cls, termo):
        return f'{cls.URL_BASE}?{urlencode({"btn-buscar": "Buscar", "txt-busca": termo})}'

    @staticmethod
    def _url_produto_valida(url):
        partes = urlparse(url)
        return (
            partes.hostname in {'gimba.com.br', 'www.gimba.com.br'}
            and bool(parse_qs(partes.query).get('PID'))
        )

    @classmethod
    def _extrair_ofertas(cls, html, limite):
        ofertas = []
        for url, textos in cls._ancoras_por_url(html).items():
            preco = next((_decimal_brasileiro(texto) for texto in textos if _decimal_brasileiro(texto)), None)
            titulos = [texto for texto in textos if texto and _decimal_brasileiro(texto) is None]
            titulo = max(titulos, key=len, default='').strip()
            codigo = (parse_qs(urlparse(url).query).get('PID') or [''])[0]
            if preco and preco > 0 and titulo and codigo:
                ofertas.append(cls._oferta(
                    codigo=codigo,
                    titulo=titulo,
                    url=url,
                    preco=preco,
                ))
        return sorted(ofertas, key=lambda oferta: (oferta['preco_total'], oferta['titulo']))[:limite]


class FidelityProvider(CatalogoHtmlProvider):
    FLAG_CONFIGURACAO = 'FIDELITY_PRICE_SEARCH_ENABLED'
    NOME = 'FIDELITY'
    ROTULO = 'Fidelity Suprimentos'
    URL_BASE = 'https://fidelitysuprimentos.com.br/'

    @classmethod
    def _url_busca(cls, termo):
        return f'{cls.URL_BASE}?{urlencode({"s": termo, "post_type": "product"})}'

    @staticmethod
    def _url_produto_valida(url):
        partes = urlparse(url)
        return (
            partes.hostname in {'fidelitysuprimentos.com.br', 'www.fidelitysuprimentos.com.br'}
            and partes.path.startswith('/produto/')
        )

    @classmethod
    def _extrair_ofertas(cls, html, limite):
        ofertas = []
        for url, textos in cls._ancoras_por_url(html).items():
            preco = next((_decimal_brasileiro(texto) for texto in textos if _decimal_brasileiro(texto)), None)
            titulos = [texto for texto in textos if texto and _decimal_brasileiro(texto) is None]
            titulo = max(titulos, key=len, default='').strip()
            codigo = urlparse(url).path.rstrip('/').rsplit('/', 1)[-1]
            if preco and preco > 0 and titulo and codigo:
                ofertas.append(cls._oferta(
                    codigo=codigo,
                    titulo=titulo,
                    url=url,
                    preco=preco,
                ))
        return sorted(ofertas, key=lambda oferta: (oferta['preco_total'], oferta['titulo']))[:limite]


class MercadoLivreProvider:
    NOME = 'MERCADO_LIVRE'
    ROTULO = 'Mercado Livre'
    ENDPOINT = 'https://api.mercadolibre.com/sites/MLB/search'

    @staticmethod
    def configurado():
        return bool(os.getenv('MERCADO_LIVRE_ACCESS_TOKEN', '').strip())

    @classmethod
    def buscar(cls, termo, limite=20):
        token = os.getenv('MERCADO_LIVRE_ACCESS_TOKEN', '').strip()
        if not token:
            raise PrecoOnlineErro(
                'A integração com o Mercado Livre ainda não possui um token configurado.'
            )

        query = urlencode({
            'q': termo,
            'sort': 'price_asc',
            'limit': max(1, min(int(limite), 50)),
        })
        requisicao = Request(
            f'{cls.ENDPOINT}?{query}',
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
                'User-Agent': 'GerenciadorEstoque/1.0',
            },
        )
        try:
            with urlopen(
                requisicao,
                timeout=getattr(settings, 'ONLINE_PRICE_SEARCH_TIMEOUT', 15),
            ) as resposta:
                dados = json.loads(resposta.read().decode('utf-8'))
        except HTTPError as erro:
            if erro.code in (401, 403):
                raise PrecoOnlineErro(
                    'A autorização do Mercado Livre expirou ou não permite pesquisas.'
                ) from erro
            raise PrecoOnlineErro(f'O Mercado Livre respondeu com erro HTTP {erro.code}.') from erro
        except (URLError, TimeoutError, json.JSONDecodeError) as erro:
            raise PrecoOnlineErro(
                'Não foi possível consultar o Mercado Livre neste momento.'
            ) from erro

        ofertas = []
        for item in dados.get('results', []):
            preco = Decimal(str(item.get('price') or '0'))
            if preco <= 0 or not item.get('permalink'):
                continue
            frete_gratis = bool((item.get('shipping') or {}).get('free_shipping'))
            frete = Decimal('0') if frete_gratis else None
            vendedor = item.get('seller') or {}
            ofertas.append({
                'fonte': cls.NOME,
                'codigo_externo': str(item.get('id') or ''),
                'titulo': str(item.get('title') or '')[:255],
                'vendedor': str(vendedor.get('nickname') or vendedor.get('id') or '')[:160],
                'url': item['permalink'],
                'preco': preco,
                'frete': frete,
                'preco_total': preco + (frete or Decimal('0')),
                'frete_conhecido': frete_gratis,
                'condicao': str(item.get('condition') or '')[:30],
            })
        return ofertas


class PrecoOnlineService:
    PROVIDERS = (GimbaProvider, FidelityProvider, MercadoLivreProvider)

    @classmethod
    def fontes_disponiveis(cls):
        return [
            {
                'codigo': provider.NOME,
                'nome': provider.ROTULO,
                'habilitada': provider.configurado(),
            }
            for provider in cls.PROVIDERS
        ]

    @classmethod
    def configurado(cls):
        return any(provider.configurado() for provider in cls.PROVIDERS)

    @classmethod
    def _provider(cls, fonte):
        fonte = (fonte or '').strip().upper()
        if fonte:
            provider = next((item for item in cls.PROVIDERS if item.NOME == fonte), None)
            if provider is None:
                raise PrecoOnlineErro('A fonte de pesquisa selecionada é inválida.')
            return provider
        return next((item for item in cls.PROVIDERS if item.configurado()), None)

    @classmethod
    @transaction.atomic
    def pesquisar(cls, *, insumo, termo, usuario, fonte=None):
        termo = (termo or insumo.descricao).strip()
        if len(termo) < 3:
            raise PrecoOnlineErro('Informe ao menos três caracteres para pesquisar.')

        provider = cls._provider(fonte)
        if provider is None:
            raise PrecoOnlineErro('Nenhuma fonte de pesquisa online está habilitada.')
        resultados = provider.buscar(termo)
        pesquisa = PesquisaPrecoOnline.objects.create(
            insumo=insumo,
            termo=termo,
            fonte=provider.NOME,
            pesquisado_por=usuario,
        )
        OfertaPrecoOnline.objects.bulk_create([
            OfertaPrecoOnline(
                pesquisa=pesquisa,
                insumo=insumo,
                **oferta,
            )
            for oferta in resultados
        ])
        return pesquisa
