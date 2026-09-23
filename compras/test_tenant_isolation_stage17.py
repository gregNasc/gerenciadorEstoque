from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from compras.models import (
    Aquisicao,
    CatalogoProdutoEmpresa,
    HistoricoPrecoProduto,
    RemessaCompra,
)
from compras.policies import AquisicaoAccessPolicy
from compras.services import AquisicaoService, ProdutoPrecoService
from estoque.models import (
    Base,
    CategoriaEquipamentoEmpresa,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Equipamento,
    Perfil,
    Produto,
    RelacionamentoEmpresa,
)
from estoque.policies.compras import ComprasAccessPolicy
from insumos.models import (
    CategoriaInsumo,
    FornecedorInsumo,
    Insumo,
    OfertaPrecoOnline,
    PrecoFornecedorInsumo,
    PesquisaPrecoOnline,
    SaldoInsumoBase,
)
from ordens_servico.models import OrdemServico
from ordens_servico.policies import OrdemServicoAccessPolicy


class Stage17TenantIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company_a = Empresa.objects.create(nome='Empresa A Etapa 17')
        cls.company_b = Empresa.objects.create(nome='Empresa B Secreta Etapa 17')
        cls.base_a = Base.objects.create(empresa=cls.company_a, nome='Base A Etapa 17')
        cls.base_b = Base.objects.create(empresa=cls.company_b, nome='Base B Secreta Etapa 17')
        cls.admin_a = cls._admin('admin.a.etapa17', cls.company_a)
        CategoriaEquipamentoEmpresa.objects.create(empresa=cls.company_a, nome='Coletores')
        CategoriaEquipamentoEmpresa.objects.create(empresa=cls.company_b, nome='Notebooks')
        cls.admin_b = cls._admin('admin.b.etapa17', cls.company_b)
        cls.product_a = Produto.objects.create(
            codigo='PROD-E17-A', descricao='Coletor permitido A', fabricante='Marca',
            modelo='A', categoria='Coletores', empresa_catalogo_origem=cls.company_a,
        )
        cls.product_b = Produto.objects.create(
            codigo='PROD-E17-B', descricao='NOTEBOOK-SECRETO-TENANT-B', fabricante='Marca',
            modelo='B', categoria='Notebooks', empresa_catalogo_origem=cls.company_b,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.company_a, produto=cls.product_a, configurado_por=cls.admin_a,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.company_a, produto=cls.product_b, ativo=False,
            configurado_por=cls.admin_a,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.company_b, produto=cls.product_b, configurado_por=cls.admin_b,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.company_b, produto=cls.product_a, ativo=False,
            configurado_por=cls.admin_b,
        )
        cls.equipment_a = Equipamento.objects.create(
            produto=cls.product_a, numero_serie='SER-E17-A', patrimonio='PAT-E17-A',
            regional=cls.base_a, codigo='EQ-E17-A', preco_referencia=Decimal('100'),
        )
        cls.equipment_b = Equipamento.objects.create(
            produto=cls.product_b, numero_serie='SER-E17-B', patrimonio='PAT-E17-B',
            regional=cls.base_b, codigo='EQ-E17-B', preco_referencia=Decimal('9999'),
        )
        cls.supplier = FornecedorInsumo.objects.create(
            nome='Fornecedor global Etapa 17', documento='17000000000100'
        )
        cls.purchase_a = Aquisicao.objects.create(
            empresa=cls.company_a, fornecedor=cls.supplier,
            cadastrado_por=cls.admin_a, numero_documento='DOC-A-17',
        )
        cls.purchase_b = Aquisicao.objects.create(
            empresa=cls.company_b, fornecedor=cls.supplier,
            cadastrado_por=cls.admin_b, numero_documento='DOC-SECRETO-B-17',
        )
        category = CategoriaInsumo.objects.create(nome='Categoria Etapa 17')
        cls.supply = Insumo.objects.create(
            descricao='Insumo Etapa 17', categoria=category, unidade_medida='UN'
        )
        SaldoInsumoBase.objects.create(
            base=cls.base_a, insumo=cls.supply, saldo=1, custo_medio=10
        )
        SaldoInsumoBase.objects.create(
            base=cls.base_b, insumo=cls.supply, saldo=1, custo_medio=9999
        )
        cls.supply_price_a = PrecoFornecedorInsumo.objects.create(
            empresa=cls.company_a,
            insumo=cls.supply,
            fornecedor=cls.supplier,
            valor_unitario=Decimal('11'),
            cadastrado_por=cls.admin_a,
        )
        cls.supply_price_b = PrecoFornecedorInsumo.objects.create(
            empresa=cls.company_b,
            insumo=cls.supply,
            fornecedor=cls.supplier,
            valor_unitario=Decimal('8888'),
            cadastrado_por=cls.admin_b,
        )

    @staticmethod
    def _admin(username, company):
        user = User.objects.create_user(username, password='Teste123!')
        user.perfil.role = Perfil.Role.ADMIN
        user.perfil.empresa = company
        user.perfil.save()
        return user

    def test_admin_purchase_and_financial_dashboards_are_tenant_scoped(self):
        self.assertEqual(
            set(AquisicaoAccessPolicy.queryset(self.admin_a)),
            {self.purchase_a},
        )
        self.client.force_login(self.admin_a)
        purchases = self.client.get(reverse('compras:aquisicao_lista'))
        equipment_values = self.client.get(reverse('compras:valores_equipamentos'))
        supply_values = self.client.get(reverse('compras:valores_insumos'))

        self.assertNotContains(purchases, 'DOC-SECRETO-B-17')
        self.assertNotContains(equipment_values, 'NOTEBOOK-SECRETO-TENANT-B')
        self.assertEqual(equipment_values.context['total_equipamentos'], 1)
        self.assertEqual(supply_values.context['total'], Decimal('10'))

    def test_company_catalog_controls_products_and_categories_for_registration(self):
        self.assertEqual(
            set(ComprasAccessPolicy.produtos_catalogo(self.admin_a)),
            {self.product_a},
        )
        self.client.force_login(self.admin_a)
        catalog_page = self.client.get(reverse('compras:catalogo_empresa'))
        self.assertNotContains(catalog_page, 'NOTEBOOK-SECRETO-TENANT-B')
        response = self.client.get(
            reverse('estoque:produtos_por_categoria'),
            {'categoria': 'Coletores', 'base': self.base_a.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['produtos'], [
            {'id': self.product_a.pk, 'descricao': self.product_a.descricao}
        ])

        forbidden = self.client.post(reverse('compras:catalogo_empresa'), {
            'empresa': self.company_b.pk,
            'produtos': [self.product_a.pk, self.product_b.pk],
        })
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(
            set(ComprasAccessPolicy.produtos_catalogo(self.admin_b)),
            {self.product_b},
        )

    def test_admin_defines_private_custom_category_for_own_company(self):
        self.client.force_login(self.admin_a)
        response = self.client.post(reverse('compras:criar_produto_catalogo'), {
            'empresa_catalogo': self.company_a.pk,
            'codigo': 'PROD-E17-CATEGORIA-LIVRE',
            'descricao': 'Equipamento categoria própria A',
            'nome_resumido': 'Equipamento próprio',
            'fabricante': 'Marca A',
            'modelo': 'Modelo A',
            'sku_fabricante': '',
            'categoria': 'Automação Especial A',
            'subcategoria': '',
            'unidade_medida': 'UN',
            'quantidade_embalagem': '1',
            'especificacoes_tecnicas': '{}',
            'ativo': 'on',
        })
        self.assertRedirects(response, reverse('compras:valores_equipamentos'))
        product = Produto.objects.get(codigo='PROD-E17-CATEGORIA-LIVRE')
        self.assertEqual(product.categoria, 'Automação Especial A')
        self.assertEqual(product.empresa_catalogo_origem, self.company_a)
        self.assertTrue(CatalogoProdutoEmpresa.objects.filter(
            empresa=self.company_a,
            produto=product,
            ativo=True,
        ).exists())

        self.client.force_login(self.admin_b)
        catalog_page = self.client.get(reverse('compras:catalogo_empresa'))
        self.assertNotContains(catalog_page, 'EQUIPAMENTO CATEGORIA PRÓPRIA A')

    def test_forged_external_price_update_is_not_resolved(self):
        self.client.force_login(self.admin_a)
        response = self.client.post(
            reverse('compras:alterar_preco_produto', args=[self.equipment_b.pk]),
            {
                'preco_referencia': '1.00',
                'preco_origem': Produto.OrigemPreco.INFORMADO_COMPRAS,
                'observacao_preco': 'Tentativa externa',
            },
        )
        self.assertEqual(response.status_code, 404)
        self.product_b.refresh_from_db()
        self.assertIsNone(self.product_b.preco_referencia)

    def test_same_product_has_independent_price_in_each_company(self):
        shared_product = Produto.objects.create(
            codigo='PROD-E17-SHARED', descricao='Produto compartilhado Etapa 17',
            fabricante='Marca', modelo='Compartilhado', categoria='Coletores',
        )
        catalog_a = CatalogoProdutoEmpresa.objects.create(
            empresa=self.company_a,
            produto=shared_product,
            configurado_por=self.admin_a,
            preco_referencia=Decimal('100'),
            preco_origem=Produto.OrigemPreco.INFORMADO_COMPRAS,
        )
        catalog_b = CatalogoProdutoEmpresa.objects.create(
            empresa=self.company_b,
            produto=shared_product,
            configurado_por=self.admin_b,
            preco_referencia=Decimal('900'),
            preco_origem=Produto.OrigemPreco.ESTIMATIVA_MERCADO,
        )
        equipment_a = Equipamento.objects.create(
            produto=shared_product, numero_serie='SER-E17-SHARED-A',
            patrimonio='PAT-E17-SHARED-A', regional=self.base_a,
            codigo='EQ-E17-SHARED-A',
        )
        equipment_b = Equipamento.objects.create(
            produto=shared_product, numero_serie='SER-E17-SHARED-B',
            patrimonio='PAT-E17-SHARED-B', regional=self.base_b,
            codigo='EQ-E17-SHARED-B',
        )

        ProdutoPrecoService.definir(
            produto=shared_product,
            empresa=self.company_a,
            usuario=self.admin_a,
            valor='250',
            origem=Produto.OrigemPreco.INFORMADO_COMPRAS,
            observacao='Revisão exclusiva da Empresa A',
            comunicar=False,
        )

        shared_product.refresh_from_db()
        catalog_a.refresh_from_db()
        catalog_b.refresh_from_db()
        equipment_a.refresh_from_db()
        equipment_b.refresh_from_db()
        self.assertIsNone(shared_product.preco_referencia)
        self.assertEqual(catalog_a.preco_referencia, Decimal('250'))
        self.assertEqual(equipment_a.preco_referencia, Decimal('250'))
        self.assertEqual(catalog_b.preco_referencia, Decimal('900'))
        self.assertEqual(equipment_b.preco_referencia, Decimal('900'))
        self.assertEqual(
            HistoricoPrecoProduto.objects.filter(
                empresa=self.company_a, produto=shared_product,
            ).count(),
            1,
        )
        self.assertFalse(
            HistoricoPrecoProduto.objects.filter(
                empresa=self.company_b, produto=shared_product,
            ).exists()
        )

    def test_supplier_quotes_and_online_offers_are_tenant_scoped(self):
        secret_search = PesquisaPrecoOnline.objects.create(
            empresa=self.company_b,
            insumo=self.supply,
            termo='PESQUISA-SECRETA-B-17',
            fonte='FIDELITY',
            pesquisado_por=self.admin_b,
        )
        secret_offer = OfertaPrecoOnline.objects.create(
            pesquisa=secret_search,
            insumo=self.supply,
            fonte='FIDELITY',
            codigo_externo='SEGREDO-B-17',
            titulo='OFERTA-SECRETA-B-17',
            vendedor='Fornecedor secreto B',
            url='https://example.com/segredo-b-17',
            preco=Decimal('7777'),
            preco_total=Decimal('7777'),
        )
        self.client.force_login(self.admin_a)
        prices = self.client.get(reverse('insumos:precos_insumos'))
        suppliers = self.client.get(reverse('insumos:fornecedores_insumos'))
        self.assertEqual(set(prices.context['precos']), {self.supply_price_a})
        self.assertEqual(
            set(suppliers.context['precos_recentes']),
            {self.supply_price_a},
        )
        self.assertEqual(
            self.client.post(
                reverse('insumos:usar_oferta_como_preco', args=[secret_offer.pk]),
            ).status_code,
            404,
        )

    def test_additional_company_requires_selection_and_catalog_capability(self):
        relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a,
            empresa_destino=self.company_b,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relationship,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.CATALOGO,
            acao=CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR,
        )
        self.assertNotIn(
            self.company_b,
            ComprasAccessPolicy.empresas(
                self.admin_a,
                action=ComprasAccessPolicy.ADMIN,
                resource=ComprasAccessPolicy.CATALOGO,
            ),
        )
        self.admin_a.perfil.empresas_acesso_adicional.add(self.company_b)
        self.assertIn(
            self.company_b,
            ComprasAccessPolicy.empresas(
                self.admin_a,
                action=ComprasAccessPolicy.ADMIN,
                resource=ComprasAccessPolicy.CATALOGO,
            ),
        )
        self.assertNotIn(
            self.company_a,
            ComprasAccessPolicy.empresas(
                self.admin_b,
                action=ComprasAccessPolicy.ADMIN,
                resource=ComprasAccessPolicy.CATALOGO,
            ),
        )

    def test_service_rejects_external_purchase_and_invalid_remittance_company(self):
        with self.assertRaises(PermissionDenied):
            AquisicaoService.criar(
                empresa=self.company_b,
                fornecedor=self.supplier,
                usuario=self.admin_a,
                itens=[{
                    'tipo_item': 'EQUIPAMENTO',
                    'produto': self.product_b,
                    'quantidade': 1,
                    'valor_unitario': 1,
                }],
            )
        with self.assertRaises(ValidationError):
            AquisicaoService.criar(
                empresa=self.company_a,
                fornecedor=self.supplier,
                usuario=self.admin_a,
                itens=[{
                    'tipo_item': 'EQUIPAMENTO',
                    'produto': self.product_b,
                    'quantidade': 1,
                    'valor_unitario': 1,
                }],
            )
        remittance = RemessaCompra(
            empresa=self.company_a,
            fluxo=RemessaCompra.Fluxo.FORNECEDOR_DIRETO,
            aquisicao=self.purchase_b,
            base_destino=self.base_a,
            criada_por=self.admin_a,
        )
        with self.assertRaises(ValidationError):
            remittance.full_clean()


class Stage17ServiceOrderIsolationTests(TestCase):
    def setUp(self):
        self.company_a = Empresa.objects.create(nome='Empresa OS A Etapa 17')
        self.company_b = Empresa.objects.create(nome='Empresa OS B Etapa 17')
        self.base_a = Base.objects.create(empresa=self.company_a, nome='Base OS A')
        self.base_b = Base.objects.create(empresa=self.company_b, nome='Base OS B')
        self.admin_a = Stage17TenantIsolationTests._admin('admin.os.a.17', self.company_a)
        self.admin_b = Stage17TenantIsolationTests._admin('admin.os.b.17', self.company_b)
        self.special = User.objects.create_user('rafael.ribeiro', password='Teste123!')
        self.special.perfil.role = Perfil.Role.OPERADOR
        self.special.perfil.empresa = self.company_a
        self.special.perfil.save()
        self.order_a = self._order(self.company_a, self.base_a, self.admin_a, 'OS-A-17')
        self.order_b = self._order(self.company_b, self.base_b, self.admin_b, 'OS-B-SECRETA-17')

    @staticmethod
    def _order(company, base, user, number):
        return OrdemServico.objects.create(
            numero=number,
            ano=2026,
            tipo=OrdemServico.Tipo.SICK,
            empresa=company,
            base_responsavel=base,
            solicitante=user,
            motivo='Teste de isolamento',
        )

    def test_admin_and_special_technician_cannot_see_external_orders(self):
        self.assertEqual(
            set(OrdemServicoAccessPolicy.queryset(self.admin_a)),
            {self.order_a},
        )
        self.assertEqual(
            set(OrdemServicoAccessPolicy.queryset(self.special)),
            {self.order_a},
        )
        self.client.force_login(self.admin_a)
        response = self.client.get(
            reverse('ordens_servico:detalhe', args=[self.order_b.pk])
        )
        self.assertEqual(response.status_code, 404)
