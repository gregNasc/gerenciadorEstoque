from datetime import date

import requests
from django.test import TestCase

from integracao.clients.caepi import (
    CaepiHttpProvider,
    CaepiLookupResult,
    CaepiLookupStatus,
)
from integracao.services.caepi_service import CaepiService


class _ProviderEncontrado:
    def consultar(self, numero_ca):
        return CaepiLookupResult(
            status=CaepiLookupStatus.FOUND,
            numero_ca=numero_ca,
            validade_ca=date(2030, 1, 31),
            source='provedor-teste',
        )


class _ProviderDivergente:
    def consultar(self, numero_ca):
        return CaepiLookupResult(
            status=CaepiLookupStatus.FOUND,
            numero_ca='OUTRO-CA',
        )


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def json(self):
        return self.payload


class _Session:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.last_call = None

    def get(self, *args, **kwargs):
        self.last_call = (args, kwargs)
        if self.error:
            raise self.error
        return self.response


class CaepiServiceTests(TestCase):
    def test_release_manual_nao_depende_de_integracao_externa(self):
        resultado = CaepiService().consultar(' ca-123 ')

        self.assertEqual(resultado.status, CaepiLookupStatus.UNAVAILABLE)
        self.assertEqual(resultado.numero_ca, 'CA-123')
        self.assertEqual(resultado.source, 'caepi-local')

    def test_provider_futuro_e_injetavel(self):
        resultado = CaepiService(_ProviderEncontrado()).consultar('ca-456')

        self.assertEqual(resultado.status, CaepiLookupStatus.FOUND)
        self.assertEqual(resultado.numero_ca, 'CA-456')
        self.assertEqual(resultado.validade_ca, date(2030, 1, 31))

    def test_rejeita_numero_vazio(self):
        with self.assertRaisesMessage(ValueError, 'Informe o número do CA'):
            CaepiService().consultar(' ')

    def test_rejeita_resposta_de_outro_ca(self):
        with self.assertRaisesMessage(ValueError, 'outro número de CA'):
            CaepiService(_ProviderDivergente()).consultar('CA-789')

    def test_sem_api_configurada_preserva_fluxo_manual(self):
        resultado = CaepiService().consultar('12345')

        self.assertEqual(resultado.status, CaepiLookupStatus.UNAVAILABLE)
        self.assertEqual(resultado.source, 'caepi-local')

    def test_provider_http_mapeia_campos_da_base_oficial(self):
        session = _Session(_Response(payload={
            'NRRegistroCA': '12345',
            'DataValidade': '31/12/2030',
            'Situacao': 'Válido',
            'RazaoSocial': 'Fabricante Exemplo',
            'NomeEquipamento': 'Calçado de segurança',
        }))
        provider = CaepiHttpProvider(
            url='https://caepi.exemplo.test/consulta',
            token='segredo',
            session=session,
        )

        resultado = provider.consultar('12345')

        self.assertEqual(resultado.status, CaepiLookupStatus.FOUND)
        self.assertEqual(resultado.validade_ca, date(2030, 12, 31))
        self.assertEqual(resultado.fabricante_importador, 'Fabricante Exemplo')
        self.assertEqual(resultado.produto, 'Calçado de segurança')
        self.assertEqual(resultado.detail, 'Válido')
        _, kwargs = session.last_call
        self.assertEqual(kwargs['params'], {'numero_ca': '12345'})
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer segredo')

    def test_provider_http_diferencia_nao_encontrado_de_indisponivel(self):
        nao_encontrado = CaepiHttpProvider(
            url='https://caepi.exemplo.test/consulta',
            session=_Session(_Response(status_code=404)),
        ).consultar('99999')
        indisponivel = CaepiHttpProvider(
            url='https://caepi.exemplo.test/consulta',
            session=_Session(error=requests.ConnectionError()),
        ).consultar('99999')

        self.assertEqual(nao_encontrado.status, CaepiLookupStatus.NOT_FOUND)
        self.assertEqual(indisponivel.status, CaepiLookupStatus.UNAVAILABLE)
