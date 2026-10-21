from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from compras.forms import CatalogoEmpresaForm
from compras.models import (
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
)
from estoque.models import Empresa, Produto
from estoque.services.ativo_capacidade_service import AtivoCapacidadeService


class AtivoCapacidadeServiceR4Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa R4', slug='empresa-r4')
        cls.produto = Produto.objects.create(
            codigo='R4-001',
            descricao='Cadeira R4',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Mobiliário',
            empresa_catalogo_origem=cls.empresa,
        )
        cls.catalogo = CatalogoProdutoEmpresa.objects.create(
            empresa=cls.empresa,
            produto=cls.produto,
            ativo=True,
        )

    def test_produto_legado_preserva_capacidades_atuais_sem_configuracao(self):
        self.assertTrue(AtivoCapacidadeService.habilitada(
            empresa=self.empresa,
            produto=self.produto,
            codigo=CapacidadeCatalogoProdutoEmpresa.PATRIMONIO_OBRIGATORIO,
        ))
        self.assertTrue(AtivoCapacidadeService.habilitada(
            empresa=self.empresa,
            produto=self.produto,
            codigo=CapacidadeCatalogoProdutoEmpresa.PERMITE_TRANSFERENCIA,
        ))
        self.assertFalse(AtivoCapacidadeService.habilitada(
            empresa=self.empresa,
            produto=self.produto,
            codigo=CapacidadeCatalogoProdutoEmpresa.CUSTODIA_PESSOAL,
        ))

    def test_configuracao_explicita_sobrepoe_padrao_legado(self):
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=self.catalogo,
            codigo=CapacidadeCatalogoProdutoEmpresa.PATRIMONIO_OBRIGATORIO,
            ativa=False,
        )
        self.assertFalse(AtivoCapacidadeService.habilitada(
            empresa=self.empresa,
            produto=self.produto,
            codigo=CapacidadeCatalogoProdutoEmpresa.PATRIMONIO_OBRIGATORIO,
        ))

    def test_lista_habilitada_respeita_padrao_e_configuracao_explicita(self):
        self.assertEqual(
            AtivoCapacidadeService.produtos_habilitados(
                empresa=self.empresa,
                codigo=CapacidadeCatalogoProdutoEmpresa.POSSUI_SERIE,
                produtos=[self.produto.pk],
            ),
            {self.produto.pk},
        )
        CapacidadeCatalogoProdutoEmpresa.objects.create(
            catalogo=self.catalogo,
            codigo=CapacidadeCatalogoProdutoEmpresa.POSSUI_SERIE,
            ativa=False,
        )
        self.assertEqual(
            AtivoCapacidadeService.produtos_habilitados(
                empresa=self.empresa,
                codigo=CapacidadeCatalogoProdutoEmpresa.POSSUI_SERIE,
                produtos=[self.produto.pk],
            ),
            set(),
        )


class CatalogoEmpresaCapacidadesR4FormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa Form R4', slug='empresa-form-r4')
        cls.superuser = User.objects.create_superuser(
            username='super-r4', email='super-r4@example.com', password='senha-teste',
        )
        cls.produto = Produto.objects.create(
            codigo='R4-FORM-001',
            descricao='Mesa R4',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Mobiliário',
            empresa_catalogo_origem=cls.empresa,
        )

    def test_exigencia_deve_estar_contida_na_capacidade(self):
        form = CatalogoEmpresaForm(data={
            'empresa': self.empresa.pk,
            'produtos': [self.produto.pk],
            'produtos_patrimonio_obrigatorio': [self.produto.pk],
        }, user=self.superuser, empresa=self.empresa)
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Todo item que exige patrimônio também deve permitir patrimônio.',
            form.non_field_errors(),
        )

    def test_salva_capacidades_por_empresa_no_catalogo(self):
        self.client.force_login(self.superuser)
        resposta = self.client.post(reverse('compras:catalogo_empresa'), {
            'empresa': self.empresa.pk,
            'produtos': [self.produto.pk],
            'produtos_individualizaveis': [self.produto.pk],
            'produtos_com_patrimonio': [self.produto.pk],
            'produtos_patrimonio_obrigatorio': [self.produto.pk],
            'produtos_com_serie': [self.produto.pk],
            'produtos_sick': [self.produto.pk],
            'produtos_manutencao': [self.produto.pk],
            'produtos_transferencia': [self.produto.pk],
            'produtos_inativacao': [self.produto.pk],
        })
        self.assertEqual(resposta.status_code, 302)
        catalogo = CatalogoProdutoEmpresa.objects.get(
            empresa=self.empresa,
            produto=self.produto,
        )
        capacidades = dict(catalogo.capacidades.values_list('codigo', 'ativa'))
        self.assertTrue(capacidades[CapacidadeCatalogoProdutoEmpresa.POSSUI_PATRIMONIO])
        self.assertTrue(capacidades[CapacidadeCatalogoProdutoEmpresa.PATRIMONIO_OBRIGATORIO])
        self.assertTrue(capacidades[CapacidadeCatalogoProdutoEmpresa.POSSUI_SERIE])
        self.assertFalse(capacidades[CapacidadeCatalogoProdutoEmpresa.SERIE_OBRIGATORIA])
        self.assertTrue(capacidades[CapacidadeCatalogoProdutoEmpresa.PERMITE_SICK])
