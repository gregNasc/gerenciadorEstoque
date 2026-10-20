from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, Equipamento, Perfil
from insumos.models import (
    AtivoInsumoIndividualizado,
    CategoriaInsumo,
    Insumo,
    MovimentacaoInsumo,
)


class AtivoInsumoIndividualizadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa Patrimônio Insumo')
        cls.base = Base.objects.create(nome='Base Patrimônio', empresa=cls.empresa)
        cls.outra_empresa = Empresa.objects.create(nome='Outro Tenant Patrimônio')
        cls.outra_base = Base.objects.create(nome='Base Oculta', empresa=cls.outra_empresa)
        cls.admin = User.objects.create_user('admin.patrimonio.insumo', password='senha')
        cls.admin.perfil.empresa = cls.empresa
        cls.admin.perfil.role = Perfil.Role.ADMIN
        cls.admin.perfil.save(update_fields=['empresa', 'role'])
        cls.categoria = CategoriaInsumo.objects.create(nome='Operacional')

    def _dados(self, patrimonio='PAT-ESCADA-001'):
        return {
            'descricao': 'Escada operacional',
            'termo_pesquisa_online': '',
            'categoria': self.categoria.pk,
            'unidade_medida': 'UN',
            'natureza': Insumo.Natureza.REUTILIZAVEL,
            'forma_controle': Insumo.FormaControle.INDIVIDUALIZADO,
            'base_lote': self.base.pk,
            'patrimonio_insumo': patrimonio,
            'estoque_minimo': '1.00',
            'estoque_maximo': '',
            'ativo': 'on',
        }

    def test_operacional_pode_receber_patrimonio_e_base(self):
        self.client.force_login(self.admin)

        resposta = self.client.post(reverse('insumos:criar_item_insumo'), self._dados())

        self.assertEqual(resposta.status_code, 302)
        ativo = AtivoInsumoIndividualizado.objects.get()
        self.assertEqual(ativo.base, self.base)
        self.assertEqual(ativo.patrimonio, 'PAT-ESCADA-001')
        self.assertEqual(ativo.insumo.natureza, Insumo.Natureza.REUTILIZAVEL)

    def test_patrimonio_e_unico_sem_diferenciar_caixa(self):
        insumo = Insumo.objects.create(
            descricao='Balança operacional',
            categoria=self.categoria,
            unidade_medida='UN',
            natureza=Insumo.Natureza.REUTILIZAVEL,
            forma_controle=Insumo.FormaControle.INDIVIDUALIZADO,
        )
        AtivoInsumoIndividualizado.objects.create(
            base=self.outra_base,
            insumo=insumo,
            patrimonio='pat-global-001',
        )
        self.client.force_login(self.admin)
        dados = self._dados('PAT-GLOBAL-001')

        resposta = self.client.post(reverse('insumos:criar_item_insumo'), dados)

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Este número de patrimônio já está cadastrado.')
        self.assertEqual(AtivoInsumoIndividualizado.objects.count(), 1)

    def test_patrimonio_nao_pode_repetir_um_equipamento(self):
        Equipamento.objects.create(
            produto=None,
            numero_serie='SERIE-EQUIP-001',
            patrimonio='PAT-EQUIP-001',
            regional=self.base,
            codigo='COD-EQUIP-001',
        )
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse('insumos:criar_item_insumo'),
            self._dados('pat-equip-001'),
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(
            resposta,
            'Este número de patrimônio já pertence a um equipamento.',
        )
        self.assertFalse(
            AtivoInsumoIndividualizado.objects.filter(
                patrimonio__iexact='PAT-EQUIP-001',
            ).exists()
        )

    def test_estoque_exibe_patrimonio_e_nao_vaza_outro_tenant(self):
        insumo = Insumo.objects.create(
            descricao='Escada estoque',
            categoria=self.categoria,
            unidade_medida='UN',
            natureza=Insumo.Natureza.REUTILIZAVEL,
            forma_controle=Insumo.FormaControle.INDIVIDUALIZADO,
        )
        MovimentacaoInsumo.objects.create(
            base=self.base, insumo=insumo, tipo='ENTRADA', quantidade=1,
            usuario=self.admin,
        )
        AtivoInsumoIndividualizado.objects.create(
            base=self.base, insumo=insumo, patrimonio='PAT-VISIVEL-001',
        )
        AtivoInsumoIndividualizado.objects.create(
            base=self.outra_base, insumo=insumo, patrimonio='PAT-OCULTO-999',
        )
        self.client.force_login(self.admin)

        resposta = self.client.get(reverse('insumos:estoque_insumos'))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'PAT-VISIVEL-001')
        self.assertNotContains(resposta, 'PAT-OCULTO-999')
        self.assertContains(resposta, 'data-detalhe-insumo')
        self.assertContains(resposta, 'modalDetalheInsumo')
        self.assertContains(resposta, 'Patrimônios nesta Base')
        self.assertNotContains(resposta, 'Preço')
        self.assertNotContains(resposta, 'Custo')
        self.assertNotContains(resposta, 'Valor médio')
        self.assertNotContains(resposta, 'R$')
