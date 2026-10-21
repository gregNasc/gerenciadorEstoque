import gzip
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from integracao.clients.caepi import CaepiDatabaseProvider, CaepiLookupStatus
from integracao.models import CaepiImportacao, CaepiRegistro
from integracao.services.caepi_import_service import CaepiImportService


HEADER = (
    'NR Registro CA;DATA DE VALIDADE;SITUACAO;NR DO PROCESSO;CNPJ;RAZAO SOCIAL;'
    'NATUREZA;EQUIPAMENTO;DESCRICAO EQUIPAMENTO;MARCA CA;REFERENCIA;COR;'
    'APROVADO PARA LAUDO;RESTRICAO LAUDO;OBSERVACAO ANALISE LAUDO;'
    'CNPJ LABORATORIO;RAZAO SOCIAL LABORATORIO;NR LAUDO;NORMA\r\n'
)
ROW = (
    '"12345";"31/12/2030";"VÁLIDO";"ignorado";"ignorado";"ignorado";'
    '"Nacional";"CALÇADO TIPO BOTINA";"Botina de segurança";"MARCA";'
    '"REF-1";"Preta";"Proteção dos pés";"";"Observação";'
    '"ignorado";"ignorado";"LAUDO-1";"ABNT 1"\r\n'
)


class GuardedUploadedFile(SimpleUploadedFile):
    def read(self, size=-1):
        if size is None or size < 0:
            raise AssertionError('O importador tentou carregar o arquivo inteiro em memória.')
        return super().read(size)


class CaepiR3GTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='super-caepi', email='super@example.test', password='senha',
        )

    def _prepare(self):
        payload = gzip.compress(
            ('\ufeff' + HEADER + ROW).encode('utf-8'), mtime=0,
        ) + b'\r\n'
        return CaepiImportService.preparar_previa(
            uploaded_file=SimpleUploadedFile('caepi.csv.gz', payload),
            user=self.superuser,
        )

    def test_importa_gzip_oficial_sem_campos_excluidos_e_publica(self):
        importacao = self._prepare()
        self.assertEqual(importacao.status, CaepiImportacao.Status.PREVIA)
        self.assertEqual(importacao.total_registros, 1)
        registro = importacao.registros.get()
        self.assertEqual(registro.numero_ca, '12345')
        self.assertFalse(hasattr(registro, 'cnpj'))
        CaepiImportService.publicar(importacao.pk)
        resultado = CaepiDatabaseProvider().consultar('12345')
        self.assertEqual(resultado.status, CaepiLookupStatus.FOUND)
        self.assertEqual(resultado.natureza, 'Nacional')
        self.assertEqual(resultado.marca, 'MARCA')
        self.assertEqual(resultado.referencia, 'REF-1')

    def test_reimportacao_identica_e_idempotente(self):
        first = self._prepare()
        second = self._prepare()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CaepiRegistro.objects.count(), 1)

    def test_leitura_e_descompactacao_sao_incrementais(self):
        payload = gzip.compress(('﻿' + HEADER + ROW).encode('utf-8'), mtime=0)
        importacao = CaepiImportService.preparar_previa(
            uploaded_file=GuardedUploadedFile('caepi-stream.csv.gz', payload),
            user=self.superuser,
        )
        self.assertEqual(importacao.status, CaepiImportacao.Status.PREVIA)
        self.assertEqual(importacao.processados, 1)

    def test_mesmo_arquivo_recupera_importacao_processando_abandonada(self):
        payload = gzip.compress(('﻿' + HEADER + ROW).encode('utf-8'), mtime=0)
        arquivo = SimpleUploadedFile('caepi-recuperacao.csv.gz', payload)
        digest, tamanho = CaepiImportService._fingerprint(arquivo)
        importacao = CaepiImportacao.objects.create(
            nome_arquivo=arquivo.name,
            sha256=digest,
            tamanho_bytes=tamanho,
            criado_por=self.superuser,
        )
        CaepiRegistro.objects.create(
            importacao=importacao,
            numero_ca='PARCIAL',
            hash_registro='f' * 64,
        )
        CaepiImportacao.objects.filter(pk=importacao.pk).update(
            atualizado_em=timezone.now() - timedelta(minutes=11),
        )

        arquivo.seek(0)
        recuperada = CaepiImportService.preparar_previa(
            uploaded_file=arquivo,
            user=self.superuser,
        )

        self.assertEqual(recuperada.pk, importacao.pk)
        self.assertEqual(recuperada.status, CaepiImportacao.Status.PREVIA)
        self.assertEqual(recuperada.total_registros, 1)
        self.assertEqual(recuperada.processados, 1)
        self.assertFalse(recuperada.registros.filter(numero_ca='PARCIAL').exists())

    def test_painel_e_publicacao_sao_exclusivos_de_superuser(self):
        comum = User.objects.create_user('comum-caepi', password='senha')
        self.client.force_login(comum)
        self.assertEqual(self.client.get(reverse('integracao:caepi_importacoes')).status_code, 403)
        importacao = self._prepare()
        self.assertEqual(self.client.post(reverse('integracao:caepi_publicar', args=[importacao.pk])).status_code, 403)

    def test_endpoint_preenche_validade_e_natureza_da_fabricacao(self):
        importacao = self._prepare()
        CaepiImportService.publicar(importacao.pk)
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('insumos:consultar_ca_epi'), {'numero_ca': '12345'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['validade_ca'], '2030-12-31')
        self.assertEqual(response.json()['natureza'], 'Nacional')
