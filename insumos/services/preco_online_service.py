import json
import os
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.db import transaction

from insumos.models import OfertaPrecoOnline, PesquisaPrecoOnline


class PrecoOnlineErro(Exception):
    pass


class MercadoLivreProvider:
    NOME = 'MERCADO_LIVRE'
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
            with urlopen(requisicao, timeout=15) as resposta:
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
    @staticmethod
    def configurado():
        return MercadoLivreProvider.configurado()

    @staticmethod
    @transaction.atomic
    def pesquisar(*, insumo, termo, usuario):
        termo = (termo or insumo.descricao).strip()
        if len(termo) < 3:
            raise PrecoOnlineErro('Informe ao menos três caracteres para pesquisar.')

        resultados = MercadoLivreProvider.buscar(termo)
        pesquisa = PesquisaPrecoOnline.objects.create(
            insumo=insumo,
            termo=termo,
            fonte=MercadoLivreProvider.NOME,
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
