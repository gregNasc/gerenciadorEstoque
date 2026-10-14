from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from estoque import test_itens_custodia_r2e as r2e_tests
from estoque.models import (
    Colaborador,
    Custodia,
    DevolucaoCustodia,
    ItemCustodia,
    ItemDevolucaoCustodia,
)
from estoque.services.custodia_devolucao_service import CustodiaDevolucaoService


TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'private': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}


@override_settings(STORAGES=TEST_STORAGES)
class DevolucaoCustodiaR2HTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        r2e_tests.ItensCustodiaR2ETests.setUpTestData.__func__(cls)

    def setUp(self):
        super().setUp()
        self.recebedor = Colaborador.objects.create(
            empresa=self.empresa,
            base=self.base,
            nome='Recebedor da Custódia',
        )
        self.item_equipamento = ItemCustodia.objects.create(
            custodia=self.custodia,
            equipamento=self.equipamento,
        )
        self.item_linha = ItemCustodia.objects.create(
            custodia=self.custodia,
            linha_movel=self.linha,
        )

    def registrar(self, itens, **overrides):
        dados = {
            'custodia': self.custodia,
            'itens': itens,
            'motivo': 'Desligamento do colaborador',
            'responsavel_recebimento': self.recebedor,
            'registrado_por': self.usuario,
            'observacao': 'Conferência presencial',
        }
        dados.update(overrides)
        return CustodiaDevolucaoService.registrar(**dados)

    def devolvido(self, item, condicao=Custodia.CondicaoGeral.BOM):
        return {
            'item_custodia': item,
            'situacao': ItemDevolucaoCustodia.Situacao.DEVOLVIDO,
            'condicao_devolucao': condicao,
        }

    def faltante(self, item):
        return {
            'item_custodia': item,
            'situacao': ItemDevolucaoCustodia.Situacao.FALTANTE,
            'observacao': 'Não apresentado',
        }

    def test_devolucao_total_finaliza_e_libera_itens_sem_apagar_historico(self):
        devolucao = self.registrar([
            self.devolvido(self.item_equipamento),
            self.devolvido(self.item_linha, Custodia.CondicaoGeral.REGULAR),
        ])

        self.custodia.refresh_from_db()
        self.item_equipamento.refresh_from_db()
        self.item_linha.refresh_from_db()
        self.assertEqual(self.custodia.status, Custodia.Status.FINALIZADA)
        self.assertFalse(self.item_equipamento.vigente)
        self.assertFalse(self.item_linha.vigente)
        self.assertIsNotNone(self.item_equipamento.devolvido_em)
        self.assertEqual(devolucao.itens.count(), 2)
        self.assertTrue(ItemCustodia.objects.filter(pk=self.item_equipamento.pk).exists())

    def test_devolucao_parcial_mantem_faltante_vigente(self):
        devolucao = self.registrar([
            self.devolvido(self.item_equipamento),
            self.faltante(self.item_linha),
        ])

        self.custodia.refresh_from_db()
        self.item_equipamento.refresh_from_db()
        self.item_linha.refresh_from_db()
        self.assertEqual(self.custodia.status, Custodia.Status.EM_DEVOLUCAO)
        self.assertFalse(self.item_equipamento.vigente)
        self.assertTrue(self.item_linha.vigente)
        self.assertIsNone(self.item_linha.devolvido_em)
        self.assertEqual(
            devolucao.itens.get(item_custodia=self.item_linha).situacao,
            ItemDevolucaoCustodia.Situacao.FALTANTE,
        )

    def test_item_faltante_pode_ser_devolvido_em_ocorrencia_posterior(self):
        primeira = self.registrar([
            self.devolvido(self.item_equipamento),
            self.faltante(self.item_linha),
        ])
        segunda = self.registrar([self.devolvido(self.item_linha)])

        self.custodia.refresh_from_db()
        self.item_linha.refresh_from_db()
        self.assertEqual(self.custodia.status, Custodia.Status.FINALIZADA)
        self.assertFalse(self.item_linha.vigente)
        self.assertEqual(self.custodia.devolucoes.count(), 2)
        self.assertTrue(DevolucaoCustodia.objects.filter(pk=primeira.pk).exists())
        self.assertTrue(DevolucaoCustodia.objects.filter(pk=segunda.pk).exists())

    def test_exige_classificacao_de_todos_os_itens_pendentes(self):
        with self.assertRaises(ValidationError) as contexto:
            self.registrar([self.devolvido(self.item_equipamento)])

        self.assertIn('itens', contexto.exception.message_dict)
        self.assertFalse(DevolucaoCustodia.objects.exists())

    def test_rejeita_item_de_outra_custodia(self):
        outra = Custodia.objects.create(
            empresa=self.empresa,
            colaborador=self.colaborador,
            base=self.base,
            registrado_por=self.usuario,
            status=Custodia.Status.RASCUNHO,
        )
        item_externo = ItemCustodia.objects.create(
            custodia=outra,
            equipamento=self.equipamento,
        )
        with self.assertRaises(ValidationError):
            self.registrar([
                self.devolvido(self.item_equipamento),
                self.devolvido(item_externo),
            ])

    def test_item_devolvido_exige_condicao(self):
        with self.assertRaises(ValidationError):
            self.registrar([
                self.devolvido(
                    self.item_equipamento,
                    Custodia.CondicaoGeral.NAO_INFORMADA,
                ),
                self.faltante(self.item_linha),
            ])
        self.assertFalse(DevolucaoCustodia.objects.exists())

    def test_responsavel_recebimento_deve_ser_do_tenant(self):
        outra_empresa = self.empresa.__class__.objects.create(nome='Outro tenant')
        outro_recebedor = Colaborador.objects.create(
            empresa=outra_empresa,
            nome='Recebedor externo',
        )
        with self.assertRaises(ValidationError) as contexto:
            self.registrar(
                [
                    self.devolvido(self.item_equipamento),
                    self.devolvido(self.item_linha),
                ],
                responsavel_recebimento=outro_recebedor,
            )
        self.assertIn('responsavel_recebimento', contexto.exception.message_dict)

    def test_data_anterior_a_entrega_e_rejeitada(self):
        data = timezone.make_aware(
            timezone.datetime.combine(
                self.custodia.data_entrega - timedelta(days=1),
                timezone.datetime.min.time(),
            )
        )
        with self.assertRaises(ValidationError) as contexto:
            self.registrar(
                [
                    self.devolvido(self.item_equipamento),
                    self.devolvido(self.item_linha),
                ],
                data_devolucao=data,
            )
        self.assertIn('data_devolucao', contexto.exception.message_dict)

    def test_devolucao_libera_responsavel_legado_do_equipamento(self):
        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.responsavel, self.colaborador.nome)

        self.registrar([
            self.devolvido(self.item_equipamento),
            self.faltante(self.item_linha),
        ])

        self.equipamento.refresh_from_db()
        self.assertEqual(self.equipamento.responsavel, '')
