from importlib import import_module

from django.apps import apps
from django.test import TestCase

from insumos.models import CategoriaInsumo, HistoricoCadastroInsumo, Insumo


class CorrecaoUnidadeEpiTests(TestCase):
    def setUp(self):
        self.migracao = import_module('insumos.migrations.0030_corrigir_unidade_epis')
        self.categoria = CategoriaInsumo.objects.create(nome='EPI')

    def test_corrige_apenas_mascara_touca_e_luva_em_caixa(self):
        mascara = Insumo.objects.create(
            descricao='Máscara descartável', categoria=self.categoria, unidade_medida='CX'
        )
        toucas = Insumo.objects.create(
            descricao='Toucas sanfonadas', categoria=self.categoria, unidade_medida='cx'
        )
        luva = Insumo.objects.create(
            descricao='Luva nitrílica', categoria=self.categoria, unidade_medida='CX'
        )
        papel = Insumo.objects.create(
            descricao='Papel sulfite', categoria=self.categoria, unidade_medida='CX'
        )

        self.migracao.corrigir_unidades(apps, None)

        for insumo in (mascara, toucas, luva):
            insumo.refresh_from_db()
            self.assertEqual(insumo.unidade_medida, 'UN')
            historico = HistoricoCadastroInsumo.objects.get(
                insumo=insumo, origem=self.migracao.ORIGEM
            )
            self.assertEqual(historico.valor_novo, 'UN')
            self.assertEqual(historico.valor_anterior.upper(), 'CX')

        papel.refresh_from_db()
        self.assertEqual(papel.unidade_medida, 'CX')

    def test_migracao_e_idempotente_e_reversivel(self):
        insumo = Insumo.objects.create(
            descricao='Máscara cirúrgica', categoria=self.categoria, unidade_medida='CX'
        )

        self.migracao.corrigir_unidades(apps, None)
        self.migracao.corrigir_unidades(apps, None)
        self.assertEqual(
            HistoricoCadastroInsumo.objects.filter(
                insumo=insumo, origem=self.migracao.ORIGEM
            ).count(),
            1,
        )

        self.migracao.reverter_unidades(apps, None)
        insumo.refresh_from_db()
        self.assertEqual(insumo.unidade_medida, 'CX')
        self.assertFalse(
            HistoricoCadastroInsumo.objects.filter(origem=self.migracao.ORIGEM).exists()
        )
