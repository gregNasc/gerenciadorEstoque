from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from compras.models import CatalogoProdutoEmpresa
from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    CategoriaEquipamentoEmpresa,
    Empresa,
    Equipamento,
    Perfil,
    Produto,
    RelacionamentoEmpresa,
    TermoEmpresa,
)


class TenantDashboardCategoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company_a = Empresa.objects.create(nome='Dashboard Tenant A')
        cls.company_b = Empresa.objects.create(nome='Dashboard Tenant B')
        cls.base_a = Base.objects.create(nome='Base Dashboard A', empresa=cls.company_a)
        cls.base_b = Base.objects.create(nome='Base Dashboard B', empresa=cls.company_b)
        cls.category_a = CategoriaEquipamentoEmpresa.objects.create(
            empresa=cls.company_a,
            nome='Máquinas Operacionais A',
            ordem=1,
        )
        cls.empty_category_a = CategoriaEquipamentoEmpresa.objects.create(
            empresa=cls.company_a,
            nome='Categoria Sem Equipamentos A',
            ordem=2,
        )
        cls.category_b = CategoriaEquipamentoEmpresa.objects.create(
            empresa=cls.company_b,
            nome='Equipamentos Secretos B',
        )
        cls.product_a = cls._product(
            'DASH-A', cls.company_a, cls.category_a.nome, 'Produto Dashboard A',
        )
        cls.product_b = cls._product(
            'DASH-B', cls.company_b, cls.category_b.nome, 'Produto Secreto B',
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.company_a, produto=cls.product_a,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.company_b, produto=cls.product_b,
        )
        cls.equipment_a = Equipamento.objects.create(
            produto=cls.product_a,
            numero_serie='DASH-SER-A',
            patrimonio='DASH-PAT-A',
            regional=cls.base_a,
            codigo='DASH-EQP-A',
        )
        cls.equipment_b = Equipamento.objects.create(
            produto=cls.product_b,
            numero_serie='DASH-SER-B',
            patrimonio='DASH-PAT-B',
            regional=cls.base_b,
            codigo='DASH-EQP-B',
        )
        cls.admin_a = User.objects.create_user('dashboard.admin.a', password='Teste123!')
        cls.admin_a.perfil.role = Perfil.Role.ADMIN
        cls.admin_a.perfil.empresa = cls.company_a
        cls.admin_a.perfil.save(update_fields=['role', 'empresa'])
        cls.superuser = User.objects.create_superuser(
            'dashboard.superuser', password='Teste123!', email='dash@example.com',
        )

    @staticmethod
    def _product(code, company, category, description):
        return Produto.objects.create(
            codigo=code,
            descricao=description,
            fabricante='Fabricante',
            modelo=code,
            categoria=category,
            empresa_catalogo_origem=company,
        )

    def setUp(self):
        self.client.force_login(self.admin_a)

    def test_dashboard_filters_cards_and_kpis_are_tenant_scoped(self):
        response = self.client.get(reverse('estoque:index'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['categorias_catalogo'],
            [self.category_a.nome, self.empty_category_a.nome],
        )
        self.assertEqual(
            list(response.context['produtos_lista']),
            [self.product_a],
        )
        self.assertEqual(list(response.context['empresas']), [self.company_a])
        self.assertEqual(response.context['rotulo_empresa_dashboard'], 'Empresa')
        cards = {
            item['nome']: item['total']
            for item in response.context['produtos_na_categoria']
        }
        self.assertEqual(cards[self.category_a.nome], 1)
        self.assertEqual(cards[self.empty_category_a.nome], 0)
        self.assertNotContains(response, self.category_b.nome)
        self.assertNotContains(response, self.product_b.descricao)
        self.assertNotContains(response, self.company_b.nome)

        payload = self.client.get(reverse('estoque:api_kpis_json')).json()
        self.assertEqual(payload['kpis']['total'], 1)
        self.assertEqual(
            set(payload['kpis_regionais'][0]['produtos']),
            {self.category_a.nome, self.empty_category_a.nome},
        )

    def test_dashboard_and_apis_reject_other_tenant_filters(self):
        self.assertEqual(
            self.client.get(
                reverse('estoque:index'),
                {'inventory': self.company_b.pk},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse('estoque:index'),
                {'produto': self.product_b.pk},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse('estoque:index'),
                {'categoria': self.category_b.nome},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse('estoque:api_kpis_json'),
                {'produto': self.product_b.pk},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse('estoque:api_regionais_produto', args=[self.product_b.pk]),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse('estoque:produtos_por_categoria'),
                {'base': self.base_a.pk, 'categoria': self.category_b.nome},
            ).status_code,
            404,
        )

    def test_resource_sharing_does_not_add_external_tenant_to_dashboard_selector(self):
        relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a,
            empresa_destino=self.company_b,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relationship,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.EQUIPAMENTOS,
            acao=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
        )
        self.admin_a.perfil.empresas_acesso_adicional.add(self.company_b)

        response = self.client.get(reverse('estoque:index'))

        self.assertEqual(list(response.context['empresas']), [self.company_a])
        self.assertNotContains(response, self.company_b.nome)
        self.assertEqual(
            self.client.get(
                reverse('estoque:index'),
                {'inventory': self.company_b.pk},
            ).status_code,
            404,
        )

    def test_dashboard_company_label_is_tenant_configurable(self):
        TermoEmpresa.objects.create(
            empresa=self.company_a,
            chave=TermoEmpresa.Chave.EMPRESA,
            valor_singular='Operação industrial',
        )

        response = self.client.get(reverse('estoque:index'))

        self.assertEqual(
            response.context['rotulo_empresa_dashboard'],
            'Operação industrial',
        )
        self.assertContains(response, 'Operação industrial')
        self.assertNotContains(response, '>Inventory<')

    def test_group_selector_requires_explicit_admin_membership(self):
        relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a, empresa_destino=self.company_b,
        )
        for resource, action in [('OPERACAO', 'ADMINISTRAR'), ('EQUIPAMENTOS', 'VISUALIZAR')]:
            CapacidadeRelacionamentoEmpresa.objects.create(
                relacionamento=relationship, recurso=resource, acao=action,
            )
        response = self.client.get(reverse('estoque:index'))
        self.assertEqual(list(response.context['empresas']), [self.company_a])
        self.admin_a.perfil.empresas_acesso_adicional.add(self.company_b)
        response = self.client.get(reverse('estoque:index'))
        self.assertEqual(set(response.context['empresas']), {self.company_a, self.company_b})
        self.admin_a.perfil.empresas_acesso_adicional.clear()
        response = self.client.get(reverse('estoque:api_kpis_json'), {'inventory': self.company_b.pk})
        self.assertEqual(response.status_code, 404)

    def test_disabled_category_is_removed_from_dashboard_and_kpis(self):
        self.category_a.ativo = False
        self.category_a.save(update_fields=['ativo'])

        response = self.client.get(reverse('estoque:index'))
        self.assertEqual(response.context['kpis_totais']['total'], 0)
        self.assertNotIn(
            self.category_a.nome,
            response.context['categorias_catalogo'],
        )
        self.assertFalse(response.context['produtos_lista'].exists())

    def test_global_view_does_not_borrow_another_company_catalog(self):
        from estoque.services.tenant_catalog_service import TenantCatalogService

        misplaced = Equipamento.objects.create(
            produto=self.product_a, regional=self.base_b,
            numero_serie='DASH-MISPLACED', patrimonio='DASH-MISPLACED',
            codigo='DASH-MISPLACED',
        )
        visible = TenantCatalogService.scope_equipment(
            Equipamento.objects.all(), self.superuser,
        )
        self.assertNotIn(misplaced, visible)
        CatalogoProdutoEmpresa.objects.create(empresa=self.company_b, produto=self.product_a)
        self.assertNotIn(misplaced, visible.all())
        CategoriaEquipamentoEmpresa.objects.create(empresa=self.company_b, nome=self.category_a.nome)
        self.assertIn(misplaced, visible.all())

    def test_superuser_company_filter_does_not_mix_tenants(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse('estoque:index'),
            {'inventory': self.company_a.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['categorias_catalogo'],
            [self.category_a.nome, self.empty_category_a.nome],
        )
        self.assertEqual(
            list(response.context['produtos_lista']),
            [self.product_a],
        )
        self.assertEqual(response.context['kpis_totais']['total'], 1)
        self.assertNotContains(response, self.category_b.nome)
