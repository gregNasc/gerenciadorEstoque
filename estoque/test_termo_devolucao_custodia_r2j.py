from hashlib import sha256

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from estoque import test_itens_custodia_r2e as r2e_tests
from estoque.models import (
    Colaborador,
    Custodia,
    ItemCustodia,
    ItemDevolucaoCustodia,
    TermoDevolucaoCustodia,
)
from estoque.services.custodia_devolucao_service import CustodiaDevolucaoService
from estoque.services.termo_devolucao_custodia_service import (
    TermoDevolucaoCustodiaService,
)
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
class TermoDevolucaoCustodiaR2JTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        r2e_tests.ItensCustodiaR2ETests.setUpTestData.__func__(cls)
        cls.recebedor = Colaborador.objects.create(
            empresa=cls.empresa,
            base=cls.base,
            nome='Recebedor da Devolução',
        )
        cls.item_equipamento = ItemCustodia.objects.create(
            custodia=cls.custodia,
            equipamento=cls.equipamento,
            condicao_entrega=Custodia.CondicaoGeral.BOM,
        )
        cls.item_linha = ItemCustodia.objects.create(
            custodia=cls.custodia,
            linha_movel=cls.linha,
            condicao_entrega=Custodia.CondicaoGeral.NOVO,
        )

    def devolvido(self, item, condicao=Custodia.CondicaoGeral.BOM):
        return {
            'item_custodia': item,
            'situacao': ItemDevolucaoCustodia.Situacao.DEVOLVIDO,
            'condicao_devolucao': condicao,
            'observacao': 'Conferido no recebimento',
        }

    def faltante(self, item):
        return {
            'item_custodia': item,
            'situacao': ItemDevolucaoCustodia.Situacao.FALTANTE,
            'observacao': 'Não apresentado pelo colaborador',
        }

    def registrar(self, itens):
        return CustodiaDevolucaoService.registrar(
            custodia=self.custodia,
            itens=itens,
            motivo='Desligamento do colaborador',
            responsavel_recebimento=self.recebedor,
            registrado_por=self.usuario,
            observacao='Conferência presencial',
        )

    def test_devolucao_gera_termo_pdf_automaticamente(self):
        devolucao = self.registrar([
            self.devolvido(self.item_equipamento),
            self.devolvido(self.item_linha),
        ])
        termo = devolucao.termo_devolucao
        with termo.arquivo_pdf.open('rb') as arquivo:
            conteudo = arquivo.read()

        self.assertTrue(conteudo.startswith(b'%PDF'))
        self.assertEqual(termo.sha256, sha256(conteudo).hexdigest())
        self.assertEqual(len(termo.dados_snapshot['itens']), 2)
        self.assertIn('termos-devolucao', termo.arquivo_pdf.name)
        self.assertEqual(TermoDevolucaoCustodia.objects.count(), 1)

    def test_termo_de_entrega_nao_e_sobrescrito(self):
        entrega = TermoEntregaCustodiaService.gerar(
            custodia=self.custodia,
            usuario=self.usuario,
        )
        nome_entrega = entrega.arquivo_pdf.name
        hash_entrega = entrega.sha256

        devolucao = self.registrar([
            self.devolvido(self.item_equipamento),
            self.devolvido(self.item_linha),
        ])

        entrega.refresh_from_db()
        self.assertEqual(entrega.arquivo_pdf.name, nome_entrega)
        self.assertEqual(entrega.sha256, hash_entrega)
        self.assertNotEqual(
            entrega.arquivo_pdf.name,
            devolucao.termo_devolucao.arquivo_pdf.name,
        )

    def test_devolucao_parcial_e_retorno_posterior_geram_termos_distintos(self):
        primeira = self.registrar([
            self.devolvido(self.item_equipamento),
            self.faltante(self.item_linha),
        ])
        segunda = self.registrar([self.devolvido(self.item_linha)])

        self.assertEqual(TermoDevolucaoCustodia.objects.count(), 2)
        self.assertNotEqual(
            primeira.termo_devolucao.arquivo_pdf.name,
            segunda.termo_devolucao.arquivo_pdf.name,
        )
        self.assertEqual(
            primeira.termo_devolucao.dados_snapshot['itens'][1]['situacao'],
            'Faltante',
        )
        self.assertEqual(
            segunda.termo_devolucao.dados_snapshot['itens'][0]['situacao'],
            'Devolvido',
        )

    def test_geracao_direta_e_idempotente(self):
        devolucao = self.registrar([
            self.devolvido(self.item_equipamento),
            self.devolvido(self.item_linha),
        ])
        primeiro = devolucao.termo_devolucao
        segundo = TermoDevolucaoCustodiaService.gerar(
            devolucao=devolucao,
            usuario=self.usuario,
        )
        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(TermoDevolucaoCustodia.objects.count(), 1)

    def test_termo_persistido_e_imutavel(self):
        devolucao = self.registrar([
            self.devolvido(self.item_equipamento),
            self.devolvido(self.item_linha),
        ])
        termo = devolucao.termo_devolucao
        termo.sha256 = '0' * 64
        with self.assertRaises(ValidationError):
            termo.save()

    def test_snapshot_contem_condicoes_sem_credenciais_moveis(self):
        devolucao = self.registrar([
            self.devolvido(self.item_equipamento, Custodia.CondicaoGeral.REGULAR),
            self.faltante(self.item_linha),
        ])
        snapshot = devolucao.termo_devolucao.dados_snapshot
        self.assertEqual(snapshot['itens'][0]['condicao_devolucao'], 'Regular')
        self.assertEqual(snapshot['itens'][1]['situacao'], 'Faltante')
        serializado = str(snapshot).casefold()
        self.assertNotIn("'pin'", serializado)
        self.assertNotIn("'puk'", serializado)
