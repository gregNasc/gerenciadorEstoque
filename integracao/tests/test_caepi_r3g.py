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

    def test_upload_web_persiste_fonte_sem_processar_na_requisicao(self):
        payload = gzip.compress(('﻿' + HEADER + ROW).encode('utf-8'), mtime=0)
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse('integracao:caepi_importacoes'),
            {'arquivo': SimpleUploadedFile('atualizado.csv.gz', payload)},
        )

        self.assertEqual(response.status_code, 302)
        importacao = CaepiImportacao.objects.get(
            nome_arquivo__iexact='atualizado.csv.gz',
        )
        self.assertEqual(importacao.status, CaepiImportacao.Status.PROCESSANDO)
        self.assertTrue(importacao.arquivo_fonte.name)
        self.assertEqual(importacao.processados, 0)
        importacao.arquivo_fonte.delete(save=False)

    def test_processamento_retomavel_avanca_cursor_sem_reenviar_arquivo(self):
        second_row = ROW.replace('12345', '67890').replace('REF-1', 'REF-2')
        payload = gzip.compress(
            ('﻿' + HEADER + ROW + second_row).encode('utf-8'), mtime=0,
        )
        importacao, deve_processar = CaepiImportService.enfileirar_previa(
            uploaded_file=SimpleUploadedFile('retomavel.csv.gz', payload),
            user=self.superuser,
        )

        primeiro = CaepiImportService.processar_lote_salvo(
            importacao.pk, max_rows=1, max_seconds=30,
        )
        segundo = CaepiImportService.processar_lote_salvo(
            importacao.pk, max_rows=1, max_seconds=30,
        )
        concluido = CaepiImportService.processar_lote_salvo(
            importacao.pk, max_rows=1, max_seconds=30,
        )

        self.assertTrue(deve_processar)
        self.assertEqual(primeiro.status, CaepiImportacao.Status.PROCESSANDO)
        self.assertEqual(primeiro.processados, 1)
        self.assertEqual(segundo.status, CaepiImportacao.Status.PROCESSANDO)
        self.assertEqual(segundo.processados, 2)
        self.assertEqual(concluido.status, CaepiImportacao.Status.PREVIA)
        self.assertEqual(concluido.total_registros, 2)
        self.assertSetEqual(
            set(concluido.registros.values_list('numero_ca', flat=True)),
            {'12345', '67890'},
        )
        concluido.arquivo_fonte.delete(save=False)

    def test_endpoint_retoma_importacao_interrompida_sem_novo_upload(self):
        payload = gzip.compress(('﻿' + HEADER + ROW).encode('utf-8'), mtime=0)
        importacao, deve_processar = CaepiImportService.enfileirar_previa(
            uploaded_file=SimpleUploadedFile('retomar.csv.gz', payload),
            user=self.superuser,
        )
        CaepiImportacao.objects.filter(pk=importacao.pk).update(
            atualizado_em=timezone.now() - timedelta(minutes=11),
        )
        self.client.force_login(self.superuser)

        response = self.client.post(reverse(
            'integracao:caepi_processar_lote', args=[importacao.pk],
        ))
        if response.json()['status'] == CaepiImportacao.Status.PROCESSANDO:
            response = self.client.post(reverse(
                'integracao:caepi_processar_lote', args=[importacao.pk],
            ))

        self.assertTrue(deve_processar)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['concluida'])
        importacao.refresh_from_db()
        self.assertEqual(importacao.status, CaepiImportacao.Status.PREVIA)
        self.assertEqual(importacao.total_registros, 1)
        self.assertTrue(importacao.arquivo_fonte.name)
        importacao.arquivo_fonte.delete(save=False)

    def test_lote_nao_exige_join_com_criador_anulavel(self):
        payload = gzip.compress(('﻿' + HEADER + ROW).encode('utf-8'), mtime=0)
        importacao, _ = CaepiImportService.enfileirar_previa(
            uploaded_file=SimpleUploadedFile('sem-criador.csv.gz', payload),
            user=self.superuser,
        )
        CaepiImportacao.objects.filter(pk=importacao.pk).update(
            criado_por=None,
            status=CaepiImportacao.Status.INTERROMPIDA,
        )

        resultado = CaepiImportService.processar_upload_salvo(importacao.pk)

        self.assertEqual(resultado.status, CaepiImportacao.Status.PREVIA)
        self.assertEqual(resultado.total_registros, 1)
        resultado.arquivo_fonte.delete(save=False)

    def test_csv_existente_reposiciona_cursor_apos_linhas_confirmadas(self):
        second_row = ROW.replace('12345', '67890').replace('REF-1', 'REF-2')
        third_row = ROW.replace('12345', '54321').replace('REF-1', 'REF-3')
        payload = ('﻿' + HEADER + ROW + second_row + third_row).encode('utf-8')
        importacao, _ = CaepiImportService.enfileirar_previa(
            uploaded_file=SimpleUploadedFile('relatorio-oficial.csv', payload),
            user=self.superuser,
        )
        parcial = CaepiImportService.processar_lote_salvo(
            importacao.pk, max_rows=1, max_seconds=30,
        )
        nome_staged = parcial.arquivo_processamento.name
        storage = parcial.arquivo_processamento.storage
        if nome_staged and storage.exists(nome_staged):
            storage.delete(nome_staged)
        CaepiImportacao.objects.filter(pk=parcial.pk).update(
            arquivo_processamento='',
            cursor_processamento=0,
            status=CaepiImportacao.Status.INTERROMPIDA,
        )

        retomada = CaepiImportService.processar_lote_salvo(
            parcial.pk, max_rows=1, max_seconds=30,
        )

        self.assertEqual(retomada.processados, 2)
        self.assertEqual(retomada.registros.count(), 2)
        self.assertSetEqual(
            set(retomada.registros.values_list('numero_ca', flat=True)),
            {'12345', '67890'},
        )
        concluida = CaepiImportService.processar_upload_salvo(retomada.pk)
        self.assertEqual(concluida.status, CaepiImportacao.Status.PREVIA)
        self.assertEqual(concluida.total_registros, 3)
        concluida.arquivo_fonte.delete(save=False)
        concluida.arquivo_processamento.delete(save=False)
