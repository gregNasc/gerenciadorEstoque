from hashlib import sha256

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from estoque import test_itens_custodia_r2e as r2e_tests
from estoque.models import Custodia, ItemCustodia, TermoEntregaCustodia
from estoque.services.termo_entrega_custodia_service import (
    TermoEntregaCustodiaService,
)


TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'private': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}


@override_settings(STORAGES=TEST_STORAGES)
class TermoEntregaCustodiaR2ITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        r2e_tests.ItensCustodiaR2ETests.setUpTestData.__func__(cls)
        cls.item_equipamento = ItemCustodia.objects.create(
            custodia=cls.custodia,
            equipamento=cls.equipamento,
            condicao_entrega=Custodia.CondicaoGeral.BOM,
            observacao='Carregador original incluso',
        )
        cls.item_linha = ItemCustodia.objects.create(
            custodia=cls.custodia,
            linha_movel=cls.linha,
            condicao_entrega=Custodia.CondicaoGeral.NOVO,
        )

    def test_gera_pdf_privado_com_multiplos_itens_e_hash(self):
        termo = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )

        with termo.arquivo_pdf.open('rb') as arquivo:
            conteudo = arquivo.read()
        self.assertTrue(conteudo.startswith(b'%PDF'))
        self.assertEqual(termo.sha256, sha256(conteudo).hexdigest())
        self.assertEqual(len(termo.dados_snapshot['itens']), 2)
        self.assertEqual(termo.dados_snapshot['schema_version'], 2)
        self.assertEqual(
            termo.dados_snapshot['custodia']['codigo'],
            f'CUS-{self.custodia.data_entrega.year}-{self.custodia.pk:04d}',
        )
        self.assertEqual(
            termo.dados_snapshot['itens'][0]['observacao_entrega'],
            'CARREGADOR ORIGINAL INCLUSO',
        )
        self.assertEqual(
            termo.dados_snapshot['itens'][0]['modelo'],
            self.produto.modelo.upper(),
        )
        self.assertIn('termos-entrega', termo.arquivo_pdf.name)

    def test_geracao_e_idempotente_e_nao_sobrescreve_arquivo(self):
        primeiro = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        segundo = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )

        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(primeiro.arquivo_pdf.name, segundo.arquivo_pdf.name)
        self.assertEqual(TermoEntregaCustodia.objects.count(), 1)

    def test_snapshot_nao_muda_apos_edicao_dos_cadastros(self):
        termo = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        snapshot = termo.dados_snapshot.copy()
        self.colaborador.nome = 'Nome alterado depois do termo'
        self.colaborador.save()
        self.produto.modelo = 'Modelo alterado depois do termo'
        self.produto.save()

        termo.refresh_from_db()
        self.assertEqual(termo.dados_snapshot, snapshot)
        self.assertNotEqual(
            termo.dados_snapshot['colaborador']['nome'],
            self.colaborador.nome,
        )

    def test_termo_persistido_e_imutavel(self):
        termo = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        termo.sha256 = '0' * 64
        with self.assertRaises(ValidationError):
            termo.save()

    def test_rascunho_nao_gera_termo(self):
        self.custodia.status = Custodia.Status.RASCUNHO
        self.custodia.save()
        with self.assertRaises(ValidationError):
            TermoEntregaCustodiaService.gerar(
                custodia=self.custodia,
                usuario=self.usuario,
            )

    def test_snapshot_nao_expoe_credenciais_da_linha(self):
        termo = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        serializado = str(termo.dados_snapshot).casefold()
        self.assertNotIn('pin', serializado)
        self.assertNotIn('puk', serializado)
        self.assertIn('iccid', serializado)
