from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from insumos.forms import InsumoForm
from insumos.models import CategoriaInsumo, Insumo


class NaturezaControleInsumoR3ATests(TestCase):
    def setUp(self):
        self.categoria_geral = CategoriaInsumo.objects.create(nome='GERAL R3A')

    def criar_insumo(self, descricao, *, categoria=None, tipo_controle='QUANTIDADE'):
        return Insumo.objects.create(
            descricao=descricao,
            categoria=categoria or self.categoria_geral,
            unidade_medida='UN',
            tipo_controle=tipo_controle,
        )

    def test_novos_insumos_preservam_comportamento_padrao(self):
        insumo = self.criar_insumo('Papel R3A')

        self.assertEqual(insumo.natureza, Insumo.Natureza.CONSUMIVEL)
        self.assertEqual(
            insumo.forma_controle,
            Insumo.FormaControle.QUANTIDADE,
        )
        self.assertEqual(insumo.tipo_controle, 'QUANTIDADE')

    def test_formulario_separa_natureza_e_forma_de_controle(self):
        form = InsumoForm()

        self.assertIn('natureza', form.fields)
        self.assertIn('forma_controle', form.fields)
        self.assertNotIn('tipo_controle', form.fields)
        self.assertNotIn('base', form.fields)

    def test_migracao_classifica_legado_sem_alterar_tipo_controle(self):
        categoria_epi = CategoriaInsumo.objects.create(nome=' EPI ')
        epi = self.criar_insumo(
            'Capacete R3A',
            categoria=categoria_epi,
            tipo_controle='REUTILIZAVEL',
        )
        reutilizavel = self.criar_insumo(
            'Grampeador R3A',
            tipo_controle='REUTILIZAVEL',
        )
        lote = self.criar_insumo('Etiqueta R3A', tipo_controle='LOTE')
        consumivel = self.criar_insumo('Caneta R3A')

        migracao = import_module(
            'insumos.migrations.0039_separar_natureza_forma_controle'
        )
        migracao.separar_natureza_forma_controle(apps, None)

        for insumo in (epi, reutilizavel, lote, consumivel):
            insumo.refresh_from_db()

        self.assertEqual(epi.natureza, Insumo.Natureza.EPI)
        self.assertEqual(
            epi.forma_controle,
            Insumo.FormaControle.QUANTIDADE,
        )
        self.assertEqual(epi.tipo_controle, 'REUTILIZAVEL')
        self.assertEqual(reutilizavel.natureza, Insumo.Natureza.REUTILIZAVEL)
        self.assertEqual(lote.natureza, Insumo.Natureza.CONSUMIVEL)
        self.assertEqual(lote.forma_controle, Insumo.FormaControle.LOTE)
        self.assertEqual(consumivel.natureza, Insumo.Natureza.CONSUMIVEL)

    def test_constraints_recusam_classificacoes_desconhecidas(self):
        insumo = self.criar_insumo('Inválido R3A')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Insumo.objects.filter(pk=insumo.pk).update(natureza='DESCONHECIDA')

    def test_superuser_abre_edicao_com_novos_campos(self):
        usuario = User.objects.create_superuser(
            username='superuser.r3a',
            email='superuser.r3a@example.com',
            password='senha-teste-r3a',
        )
        insumo = self.criar_insumo('Insumo editável R3A')
        self.client.force_login(usuario)

        resposta = self.client.get(
            reverse('insumos:editar_insumos', args=[insumo.pk]),
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Natureza')
        self.assertContains(resposta, 'Forma de controle')
        self.assertNotIn('base', resposta.context['form'].fields)
