from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from compras.forms import CatalogoEmpresaForm
from compras.models import Aquisicao, CatalogoProdutoEmpresa, ItemAquisicao
from estoque.models import Empresa, Perfil, Produto
from estoque.policies.compras import ComprasAccessPolicy
from insumos.models import FornecedorInsumo


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CatalogFailClosedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inventory_brasil = Empresa.objects.create(
            nome='Inventory Brasil', slug='inventory-brasil',
        )
        cls.inventory_latam = Empresa.objects.create(
            nome='Inventory Latam', slug='inventory-latam',
        )
        cls.oxxo = Empresa.objects.create(nome='OXXO', slug='oxxo')
        cls.external_a = Empresa.objects.create(nome='Tenant externo A')
        cls.external_b = Empresa.objects.create(nome='Tenant externo B')

        cls.admin_inventory = cls._admin('admin.inventory.catalogo', cls.inventory_brasil)
        cls.admin_inventory.perfil.empresas_acesso_adicional.add(
            cls.inventory_latam, cls.oxxo,
        )
        cls.admin_latam = cls._admin('admin.latam.catalogo', cls.inventory_latam)
        cls.admin_oxxo = cls._admin('admin.oxxo.catalogo', cls.oxxo)
        cls.admin_a = cls._admin('admin.a.catalogo', cls.external_a)
        cls.admin_b = cls._admin('admin.b.catalogo', cls.external_b)
        cls.superuser = User.objects.create_superuser(
            'super.catalogo', password='Teste123!', email='super@example.com',
        )

        cls.legacy_global = cls._product('CAT-GLOBAL', None, 'Legado Inventory')
        cls.inventory_product = cls._product(
            'CAT-INVENTORY', cls.inventory_brasil, 'Produto Inventory',
        )
        cls.product_a = cls._product('CAT-A', cls.external_a, 'Produto A')
        cls.product_b = cls._product('CAT-B', cls.external_b, 'Produto B')
        cls.unconfigured_a = cls._product(
            'CAT-A-SEM-VINCULO', cls.external_a, 'Produto A sem vínculo',
        )

        for company in (cls.inventory_brasil, cls.inventory_latam, cls.oxxo):
            CatalogoProdutoEmpresa.objects.create(
                empresa=company,
                produto=cls.legacy_global,
                ativo=True,
            )
            CatalogoProdutoEmpresa.objects.create(
                empresa=company,
                produto=cls.inventory_product,
                ativo=True,
            )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.external_a, produto=cls.product_a, ativo=True,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.external_b, produto=cls.product_b, ativo=True,
        )

    @staticmethod
    def _admin(username, company):
        user = User.objects.create_user(username, password='Teste123!')
        user.perfil.role = Perfil.Role.ADMIN
        user.perfil.empresa = company
        user.perfil.save(update_fields=['role', 'empresa'])
        return user

    @staticmethod
    def _product(code, owner, description):
        return Produto.objects.create(
            codigo=code,
            descricao=description,
            fabricante='Fabricante',
            modelo=code,
            categoria='Categoria de teste',
            empresa_catalogo_origem=owner,
        )

    @staticmethod
    def _codes(user, company=None):
        return set(
            ComprasAccessPolicy.produtos_catalogo(
                user, empresa=company,
            ).values_list('codigo', flat=True)
        )

    def _product_payload(self, company, code):
        return {
            'empresa_catalogo': company.pk,
            'codigo': code,
            'descricao': f'Produto {code}',
            'nome_resumido': code,
            'fabricante': 'Fabricante',
            'modelo': code,
            'sku_fabricante': '',
            'categoria': 'Categoria própria',
            'subcategoria': '',
            'unidade_medida': 'UN',
            'quantidade_embalagem': '1',
            'especificacoes_tecnicas': '{}',
            'ativo': 'on',
        }

    def test_catalog_is_explicit_for_inventory_external_tenants_and_superuser(self):
        inventory_codes = {'CAT-GLOBAL', 'CAT-INVENTORY'}
        cases = (
            ('Inventory Brasil', self.admin_inventory, inventory_codes),
            ('Inventory LATAM', self.admin_latam, inventory_codes),
            ('OXXO', self.admin_oxxo, inventory_codes),
            ('Tenant externo A', self.admin_a, {'CAT-A'}),
            ('Tenant externo B', self.admin_b, {'CAT-B'}),
            (
                'Superuser',
                self.superuser,
                inventory_codes | {'CAT-A', 'CAT-B'},
            ),
        )

        for label, user, expected in cases:
            with self.subTest(profile=label):
                self.assertEqual(self._codes(user), expected)

    def test_company_without_explicit_configuration_receives_no_product(self):
        empty_company = Empresa.objects.create(nome='Tenant sem catálogo')
        empty_admin = self._admin('admin.sem.catalogo', empty_company)

        self.assertFalse(
            ComprasAccessPolicy.produtos_catalogo(empty_admin).exists()
        )
        self.assertNotIn('CAT-A-SEM-VINCULO', self._codes(self.admin_a))

    def test_external_admin_catalog_form_hides_global_and_other_tenant_products(self):
        form = CatalogoEmpresaForm(
            user=self.admin_a,
            empresa=self.external_a,
        )
        codes = set(form.fields['produtos'].queryset.values_list('codigo', flat=True))

        self.assertIn('CAT-A', codes)
        self.assertIn('CAT-A-SEM-VINCULO', codes)
        self.assertNotIn('CAT-GLOBAL', codes)
        self.assertNotIn('CAT-INVENTORY', codes)
        self.assertNotIn('CAT-B', codes)

    def test_product_creation_requires_authorized_owner_and_allows_code_per_tenant(self):
        url = reverse('compras:criar_produto_catalogo')

        self.client.force_login(self.admin_a)
        first = self.client.post(
            url, self._product_payload(self.external_a, 'CODIGO-COMUM'),
        )
        self.assertEqual(first.status_code, 302)

        same_as_legacy_global = self.client.post(
            url, self._product_payload(self.external_a, 'CAT-GLOBAL'),
        )
        self.assertEqual(same_as_legacy_global.status_code, 302)
        self.assertTrue(Produto.objects.filter(
            codigo='CAT-GLOBAL',
            empresa_catalogo_origem=self.external_a,
        ).exists())

        forged = self.client.post(
            url, self._product_payload(self.external_b, 'CODIGO-FORJADO'),
        )
        self.assertEqual(forged.status_code, 200)
        self.assertFalse(Produto.objects.filter(codigo='CODIGO-FORJADO').exists())

        duplicate = self.client.post(
            url, self._product_payload(self.external_a, 'CODIGO-COMUM'),
        )
        self.assertEqual(duplicate.status_code, 200)

        self.client.force_login(self.admin_b)
        second_tenant = self.client.post(
            url, self._product_payload(self.external_b, 'CODIGO-COMUM'),
        )
        self.assertEqual(second_tenant.status_code, 302)
        self.assertEqual(
            Produto.objects.filter(codigo='CODIGO-COMUM').count(),
            2,
        )

    def test_database_rejects_duplicate_code_inside_same_owner(self):
        self._product('CODIGO-REPETIDO', self.external_a, 'Primeiro')

        with self.assertRaises(IntegrityError), transaction.atomic():
            self._product('CODIGO-REPETIDO', self.external_a, 'Segundo')

        self._product('CODIGO-REPETIDO', self.external_b, 'Outro tenant')

    def test_purchase_item_rejects_product_when_company_has_no_catalog_link(self):
        supplier = FornecedorInsumo.objects.create(
            nome='Fornecedor fail closed', documento='99000000000100',
        )
        purchase = Aquisicao.objects.create(
            empresa=self.external_a,
            fornecedor=supplier,
            cadastrado_por=self.admin_a,
        )
        item = ItemAquisicao(
            aquisicao=purchase,
            tipo_item=ItemAquisicao.Tipo.EQUIPAMENTO,
            produto=self.unconfigured_a,
            quantidade=1,
            valor_unitario=1,
        )

        with self.assertRaises(ValidationError):
            item.full_clean()


class CatalogCompatibilityDataMigrationTests(TestCase):
    def test_migration_preserves_inventory_and_does_not_share_external_products(self):
        inventory_brasil = Empresa.objects.create(
            nome='Inventory Brasil', slug='inventory-brasil',
        )
        inventory_latam = Empresa.objects.create(
            nome='Inventory Latam', slug='inventory-latam',
        )
        oxxo = Empresa.objects.create(nome='OXXO', slug='oxxo')
        external = Empresa.objects.create(nome='Tenant externo da migration')
        global_product = CatalogFailClosedTests._product(
            'MIG-GLOBAL', None, 'Global legado',
        )
        inventory_product = CatalogFailClosedTests._product(
            'MIG-INVENTORY', inventory_brasil, 'Produto do grupo',
        )
        external_product = CatalogFailClosedTests._product(
            'MIG-EXTERNAL', external, 'Produto externo',
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=inventory_brasil,
            produto=global_product,
            ativo=False,
        )

        migration = import_module('estoque.migrations.0053_catalogo_fail_closed')
        migration.preserve_explicit_catalogs(
            apps,
            SimpleNamespace(connection=connection),
        )

        for company in (inventory_latam, oxxo):
            with self.subTest(company=company.nome):
                self.assertTrue(CatalogoProdutoEmpresa.objects.filter(
                    empresa=company,
                    produto=global_product,
                    ativo=True,
                ).exists())
                self.assertTrue(CatalogoProdutoEmpresa.objects.filter(
                    empresa=company,
                    produto=inventory_product,
                    ativo=True,
                ).exists())
                self.assertFalse(CatalogoProdutoEmpresa.objects.filter(
                    empresa=company,
                    produto=external_product,
                ).exists())

        self.assertFalse(CatalogoProdutoEmpresa.objects.get(
            empresa=inventory_brasil,
            produto=global_product,
        ).ativo)
        self.assertTrue(CatalogoProdutoEmpresa.objects.filter(
            empresa=external,
            produto=external_product,
            ativo=True,
        ).exists())
        self.assertFalse(CatalogoProdutoEmpresa.objects.filter(
            empresa=external,
            produto=global_product,
        ).exists())
