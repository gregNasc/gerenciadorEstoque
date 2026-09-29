import tempfile

from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from compras.models import CatalogoProdutoEmpresa
from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    CategoriaEquipamentoEmpresa,
    Empresa,
    Equipamento,
    Modulo,
    ModuloEmpresa,
    Perfil,
    Produto,
    RelacionamentoEmpresa,
    ResolucaoDocumento,
    SecaoDocumentacaoEmpresa,
    TermoEmpresa,
)
from estoque.security import secure_tenant_group_company_queryset
from estoque.services.documentation_service import DocumentationService
from estoque.services.tenant_catalog_service import TenantCatalogService
from estoque.services.tenant_terminology_service import TenantTerminologyService
from estoque.tenant_features import TenantFeatureService
from estoque.tenant_scope import TenantScope


class MultitenantFinalRegressionStageJTests(TestCase):
    """Cenário final A/B/Grupo Inventory exigido pelo Adicional J."""

    @classmethod
    def setUpTestData(cls):
        TenantFeatureService.ensure_catalog()
        cls.superuser = User.objects.create_superuser(
            username='regressao-j-superuser',
            email='regressao-j@example.test',
            password=None,
        )

        cls.company_a = Empresa.objects.create(nome='Tenant externo Alpha')
        cls.company_b = Empresa.objects.create(nome='Tenant externo Beta')
        cls.inventory = Empresa.objects.create(nome='Inventory Brasil J')
        cls.latam = Empresa.objects.create(nome='Inventory LATAM J')
        cls.oxxo = Empresa.objects.create(nome='OXXO J')

        cls.base_a = Base.objects.create(nome='Unidade Alpha', empresa=cls.company_a)
        cls.base_b = Base.objects.create(nome='Unidade Beta', empresa=cls.company_b)
        cls.base_inventory = Base.objects.create(nome='Inventory Matriz', empresa=cls.inventory)
        cls.base_latam = Base.objects.create(nome='LATAM Matriz', empresa=cls.latam)
        cls.base_oxxo = Base.objects.create(nome='OXXO Matriz', empresa=cls.oxxo)

        cls.admin_a = cls._admin('regressao-j-admin-a', cls.company_a)
        cls.admin_b = cls._admin('regressao-j-admin-b', cls.company_b)
        cls.admin_inventory = cls._admin(
            'regressao-j-admin-inventory',
            cls.inventory,
        )

        for company in (
            cls.company_a,
            cls.company_b,
            cls.inventory,
            cls.latam,
            cls.oxxo,
        ):
            for code in (
                Modulo.Codigo.ESTOQUE,
                Modulo.Codigo.EQUIPAMENTOS,
                Modulo.Codigo.SICK,
            ):
                TenantFeatureService.configure(
                    tenant=company,
                    codigo=code,
                    enabled=True,
                    actor=cls.superuser,
                )

        ModuloEmpresa.objects.filter(
            empresa=cls.company_a,
            modulo__codigo=Modulo.Codigo.SICK,
        ).update(nome_exibicao='Manutenção')
        ModuloEmpresa.objects.filter(
            empresa=cls.company_b,
            modulo__codigo=Modulo.Codigo.SICK,
        ).update(nome_exibicao='Oficina')
        TermoEmpresa.objects.create(
            empresa=cls.company_a,
            chave=TermoEmpresa.Chave.EQUIPAMENTO,
            valor_singular='Máquina',
            valor_plural='Máquinas',
        )
        TermoEmpresa.objects.create(
            empresa=cls.company_b,
            chave=TermoEmpresa.Chave.EQUIPAMENTO,
            valor_singular='Ativo',
            valor_plural='Ativos',
        )

        cls.category_a = CategoriaEquipamentoEmpresa.objects.create(
            empresa=cls.company_a,
            nome='Linha exclusiva Alpha',
        )
        cls.category_b = CategoriaEquipamentoEmpresa.objects.create(
            empresa=cls.company_b,
            nome='Linha exclusiva Beta',
        )
        cls.category_inventory = CategoriaEquipamentoEmpresa.objects.create(
            empresa=cls.inventory,
            nome='Coletores Inventory',
        )

        cls.product_a = Produto.objects.create(
            codigo='REG-J-ALPHA',
            descricao='Prensa exclusiva Alpha',
            fabricante='Alpha',
            modelo='A1',
            categoria=cls.category_a.nome,
            empresa_catalogo_origem=cls.company_a,
        )
        cls.product_b = Produto.objects.create(
            codigo='REG-J-BETA',
            descricao='Ativo exclusivo Beta',
            fabricante='Beta',
            modelo='B1',
            categoria=cls.category_b.nome,
            empresa_catalogo_origem=cls.company_b,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.company_a,
            produto=cls.product_a,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=cls.company_b,
            produto=cls.product_b,
        )
        Equipamento.objects.create(
            produto=cls.product_a,
            regional=cls.base_a,
            numero_serie='REG-J-SERIE-A',
            patrimonio='REG-J-PAT-A',
            codigo='REG-J-EQP-A',
            status='ATIVO',
        )
        Equipamento.objects.create(
            produto=cls.product_b,
            regional=cls.base_b,
            numero_serie='REG-J-SERIE-B',
            patrimonio='REG-J-PAT-B',
            codigo='REG-J-EQP-B',
            status='ATIVO',
        )

        for destination in (cls.latam, cls.oxxo):
            relationship = RelacionamentoEmpresa.objects.create(
                empresa_origem=cls.inventory,
                empresa_destino=destination,
                criado_por=cls.superuser,
            )
            CapacidadeRelacionamentoEmpresa.objects.create(
                relacionamento=relationship,
                recurso=CapacidadeRelacionamentoEmpresa.Recurso.OPERACAO,
                acao=CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR,
                criado_por=cls.superuser,
            )
        cls.admin_inventory.perfil.empresas_acesso_adicional.add(
            cls.latam,
            cls.oxxo,
        )

    @staticmethod
    def _admin(username, company):
        user = User.objects.create_user(username=username, password=None)
        user.perfil.role = Perfil.Role.ADMIN
        user.perfil.empresa = company
        user.perfil.save(update_fields=('role', 'empresa'))
        return user

    def test_new_external_tenant_starts_empty_and_enables_only_selected_modules(self):
        self.client.force_login(self.superuser)
        data_url = reverse(
            'estoque:onboarding_empresa_etapa',
            args=('dados',),
        )
        response = self.client.post(data_url, {
            'nome': 'Tenant externo recém-criado J',
            'slug': 'tenant-externo-recem-criado-j',
        })
        fresh = Empresa.objects.get(slug='tenant-externo-recem-criado-j')
        fresh_admin = self._admin('regressao-j-admin-fresh', fresh)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(fresh.ativa)
        self.assertFalse(
            CategoriaEquipamentoEmpresa.objects.filter(empresa=fresh).exists()
        )
        self.assertFalse(
            Produto.objects.filter(empresa_catalogo_origem=fresh).exists()
        )
        self.assertFalse(
            SecaoDocumentacaoEmpresa.objects.filter(empresa=fresh).exists()
        )
        self.assertFalse(DocumentationService._legacy_catalog(fresh_admin))
        self.assertFalse(TenantFeatureService.enabled_features(fresh))

        modules_url = (
            reverse('estoque:onboarding_empresa_etapa', args=('modulos',))
            + f'?empresa={fresh.pk}'
        )
        response = self.client.post(modules_url, {
            'modulos': [Modulo.Codigo.CHAMADOS],
        })

        self.assertEqual(response.status_code, 302)
        self.assertSetEqual(
            set(ModuloEmpresa.objects.filter(
                empresa=fresh,
                habilitado=True,
            ).values_list('modulo__codigo', flat=True)),
            {Modulo.Codigo.CHAMADOS},
        )
        self.assertFalse(TenantFeatureService.enabled_features(fresh))

    def test_each_tenant_keeps_its_own_terminology_in_service_and_ui(self):
        labels_a = TenantTerminologyService.labels(self.company_a)
        labels_b = TenantTerminologyService.labels(self.company_b)
        modules_a = TenantTerminologyService.module_labels(self.company_a)
        modules_b = TenantTerminologyService.module_labels(self.company_b)

        self.assertEqual(labels_a['equipamento']['plural'], 'Máquinas')
        self.assertEqual(labels_b['equipamento']['plural'], 'Ativos')
        self.assertEqual(modules_a[Modulo.Codigo.SICK], 'Manutenção')
        self.assertEqual(modules_b[Modulo.Codigo.SICK], 'Oficina')

        self.client.force_login(self.admin_a)
        response_a = self.client.get(reverse('estoque:index'))
        self.assertContains(response_a, 'Manutenção')
        self.assertContains(response_a, 'Máquinas')
        self.assertNotContains(response_a, 'Oficina')

        self.client.force_login(self.admin_b)
        response_b = self.client.get(reverse('estoque:index'))
        self.assertContains(response_b, 'Oficina')
        self.assertContains(response_b, 'Ativos')
        self.assertNotContains(response_b, 'Manutenção')

    def test_catalog_and_dashboard_are_isolated_until_explicit_share(self):
        products_a = TenantCatalogService.products(self.admin_a)
        products_b = TenantCatalogService.products(self.admin_b)
        products_inventory = TenantCatalogService.products(self.admin_inventory)

        self.assertIn(self.product_a, products_a)
        self.assertNotIn(self.product_a, products_b)
        self.assertNotIn(self.product_a, products_inventory)

        self.client.force_login(self.admin_a)
        dashboard_a = self.client.get(reverse('estoque:index'))
        self.assertContains(dashboard_a, self.product_a.descricao)
        self.assertContains(dashboard_a, self.category_a.nome)
        self.assertNotContains(dashboard_a, self.product_b.descricao)
        self.assertNotContains(dashboard_a, self.category_b.nome)

        CategoriaEquipamentoEmpresa.objects.create(
            empresa=self.company_b,
            nome=self.category_a.nome,
        )
        CatalogoProdutoEmpresa.objects.create(
            empresa=self.company_b,
            produto=self.product_a,
            configurado_por=self.superuser,
        )

        self.assertIn(self.product_a, TenantCatalogService.products(self.admin_b))
        self.assertNotIn(
            self.product_a,
            TenantCatalogService.products(self.admin_inventory),
        )

    def test_inventory_group_remains_explicit_and_operational(self):
        visible = set(TenantScope.for_user(
            self.admin_inventory,
        ).visible_companies())
        manageable = set(secure_tenant_group_company_queryset(
            Empresa.objects.all(),
            self.admin_inventory,
        ))

        expected = {self.inventory, self.latam, self.oxxo}
        self.assertSetEqual(visible, expected)
        self.assertSetEqual(manageable, expected)
        self.assertNotIn(self.company_a, manageable)
        self.assertNotIn(self.company_b, manageable)
        for company in expected:
            self.assertTrue(
                TenantFeatureService.has_feature(company, Modulo.Codigo.ESTOQUE)
            )

    def test_disabled_audits_hide_menu_and_block_page_and_write_endpoint(self):
        TenantFeatureService.configure(
            tenant=self.company_a,
            codigo=Modulo.Codigo.AUDITORIAS,
            enabled=False,
            actor=self.superuser,
        )
        self.client.force_login(self.admin_a)

        dashboard = self.client.get(reverse('estoque:index'))
        audit_url = reverse('auditorias:campanha_lista')
        self.assertEqual(dashboard.status_code, 200)
        self.assertNotContains(dashboard, f'href="{audit_url}"')
        self.assertEqual(self.client.get(audit_url).status_code, 403)
        self.assertEqual(
            self.client.post(reverse(
                'auditorias:registrar_leitura',
                args=(999999,),
            ), {'codigo': 'REG-J'}).status_code,
            403,
        )
        self.assertTrue(
            TenantFeatureService.has_feature(
                self.company_a,
                Modulo.Codigo.ESTOQUE,
            )
        )


class MultitenantFinalDocumentationRegressionStageJTests(TestCase):
    def setUp(self):
        TenantFeatureService.ensure_catalog()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_field = ResolucaoDocumento._meta.get_field('arquivo')
        self.original_storage = self.file_field.storage
        self.file_field.storage = FileSystemStorage(location=self.temp_dir.name)

        self.superuser = User.objects.create_superuser(
            'regressao-j-doc-superuser',
            email='regressao-j-doc@example.test',
            password=None,
        )
        self.company_a = Empresa.objects.create(nome='Documentação final A')
        self.company_b = Empresa.objects.create(nome='Documentação final B')
        self.admin_a = self._admin('regressao-j-doc-a', self.company_a)
        self.admin_b = self._admin('regressao-j-doc-b', self.company_b)
        for company in (self.company_a, self.company_b):
            TenantFeatureService.configure(
                tenant=company,
                codigo=Modulo.Codigo.DOCUMENTACAO,
                enabled=True,
                actor=self.superuser,
            )
            SecaoDocumentacaoEmpresa.objects.create(
                empresa=company,
                codigo=SecaoDocumentacaoEmpresa.Codigo.RESOLUCOES,
                habilitado=True,
            )

    def tearDown(self):
        self.file_field.storage = self.original_storage
        self.temp_dir.cleanup()
        super().tearDown()

    @staticmethod
    def _admin(username, company):
        user = User.objects.create_user(username=username, password=None)
        user.perfil.role = Perfil.Role.ADMIN
        user.perfil.empresa = company
        user.perfil.save(update_fields=('role', 'empresa'))
        return user

    def test_document_and_direct_file_id_from_a_are_blocked_for_b(self):
        document = ResolucaoDocumento.objects.create(
            empresa=self.company_a,
            titulo='Procedimento exclusivo Alpha J',
            fabricante='Alpha',
            modelo='AX',
            categoria='Linha Alpha',
            arquivo=SimpleUploadedFile(
                'procedimento-alpha.pdf',
                b'%PDF-1.4 tenant alpha',
                content_type='application/pdf',
            ),
            nome_original='procedimento-alpha.pdf',
            criado_por=self.admin_a,
        )
        direct_url = reverse(
            'estoque:documentacao_resolucao_arquivo',
            args=(document.pk,),
        )

        self.client.force_login(self.admin_b)
        listing_b = self.client.get(reverse('estoque:documentacao_resolucao'))
        self.assertEqual(listing_b.status_code, 200)
        self.assertNotContains(listing_b, document.titulo)
        self.assertEqual(self.client.get(direct_url).status_code, 404)

        self.client.force_login(self.admin_a)
        self.assertContains(
            self.client.get(reverse('estoque:documentacao_resolucao')),
            document.titulo,
        )
        direct_response = self.client.get(direct_url)
        self.assertEqual(direct_response.status_code, 200)
        direct_response.close()
