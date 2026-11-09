from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, Perfil
from insumos.constants import GruposInsumos


class PerfilComprasR7CTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa perfil Compras R7C')
        cls.base = Base.objects.create(nome='Base perfil Compras R7C', empresa=cls.empresa)
        cls.compras = User.objects.create_user('compras.r7c', password='teste')
        cls.compras.perfil.role = Perfil.Role.OPERADOR
        cls.compras.perfil.empresa = cls.empresa
        cls.compras.perfil.save()
        cls.compras.perfil.regionais.add(cls.base)
        cls.compras.perfil.bases_escopo_compras.add(cls.base)
        cls.compras.perfil.empresas_escopo_compras.add(cls.empresa)
        grupo, _ = Group.objects.get_or_create(name=GruposInsumos.COMPRAS)
        cls.compras.groups.add(grupo)

        cls.operador = User.objects.create_user('operador.r7c', password='teste')
        cls.operador.perfil.role = Perfil.Role.OPERADOR
        cls.operador.perfil.empresa = cls.empresa
        cls.operador.perfil.save()
        cls.operador.perfil.regionais.add(cls.base)

    def test_compras_acessa_precos_quantidades_estoque_e_aquisicoes(self):
        self.client.force_login(self.compras)
        urls = (
            reverse('insumos:estoque_insumos'),
            reverse('insumos:dashboard_saude_insumos'),
            reverse('insumos:dashboard_saude_equipamentos'),
            reverse('insumos:dashboard_saude_geral'),
            reverse('insumos:dashboard_custos'),
            reverse('insumos:precos_insumos'),
            reverse('insumos:pesquisa_precos_online'),
            reverse('compras:painel'),
            reverse('compras:aquisicao_lista'),
            reverse('compras:fornecedores_empresa'),
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_operador_comum_nao_herda_telas_de_compras(self):
        self.client.force_login(self.operador)
        for url in (
            reverse('insumos:estoque_insumos'),
            reverse('insumos:dashboard_saude_insumos'),
            reverse('insumos:dashboard_custos'),
            reverse('insumos:precos_insumos'),
            reverse('insumos:pesquisa_precos_online'),
            reverse('compras:painel'),
            reverse('compras:aquisicao_lista'),
            reverse('compras:fornecedores_empresa'),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_painel_orienta_o_perfil_compras_sem_expor_catalogo(self):
        self.client.force_login(self.compras)

        resposta = self.client.get(reverse('compras:painel'))

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Painel de Compras')
        self.assertContains(resposta, 'Solicitações para tratar')
        self.assertContains(resposta, 'Cotações em andamento')
        self.assertContains(resposta, 'Aquisições em rascunho')
        self.assertContains(resposta, 'Remessas pendentes')
        self.assertNotContains(
            resposta,
            reverse('compras:catalogo_empresa'),
        )
