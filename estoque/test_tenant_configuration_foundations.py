from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from estoque.models import (
    CategoriaEquipamentoEmpresa,
    Empresa,
    ModuloEmpresa,
    Produto,
    SecaoDocumentacaoEmpresa,
    TermoEmpresa,
)


class TenantConfigurationFoundationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Tenant configurável')
        cls.outra_empresa = Empresa.objects.create(nome='Outro tenant configurável')

    def test_new_company_starts_without_categories_terms_or_documentation_sections(self):
        self.assertFalse(self.empresa.categorias_equipamento.exists())
        self.assertFalse(self.empresa.termos_personalizados.exists())
        self.assertFalse(self.empresa.secoes_documentacao.exists())

    def test_module_display_name_falls_back_to_platform_name(self):
        configuration = ModuloEmpresa.objects.select_related('modulo').filter(
            empresa=self.empresa,
        ).first()

        self.assertIsNotNone(configuration)
        self.assertEqual(configuration.nome_apresentacao, configuration.modulo.nome)

        configuration.nome_exibicao = 'Nome personalizado'
        self.assertEqual(configuration.nome_apresentacao, 'Nome personalizado')

    def test_terms_accept_only_catalogued_keys_and_are_unique_per_company(self):
        TermoEmpresa.objects.create(
            empresa=self.empresa,
            chave=TermoEmpresa.Chave.EQUIPAMENTO,
            valor_singular='Máquina',
            valor_plural='Máquinas',
        )

        invalid = TermoEmpresa(
            empresa=self.empresa,
            chave='chave-inventada',
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            TermoEmpresa.objects.create(
                empresa=self.empresa,
                chave=TermoEmpresa.Chave.EQUIPAMENTO,
            )

    def test_categories_are_unique_only_inside_each_company(self):
        CategoriaEquipamentoEmpresa.objects.create(
            empresa=self.empresa,
            nome='Máquinas operacionais',
        )
        CategoriaEquipamentoEmpresa.objects.create(
            empresa=self.outra_empresa,
            nome='Máquinas operacionais',
        )

        with self.assertRaises(ValidationError):
            CategoriaEquipamentoEmpresa.objects.create(
                empresa=self.empresa,
                nome='Máquinas operacionais',
            )

    def test_category_aliases_and_capacity_reference_are_validated_per_company(self):
        category = CategoriaEquipamentoEmpresa.objects.create(
            empresa=self.empresa,
            nome='Scanners',
            aliases=[' scanner ', 'Scanner', 'scanners industriais'],
            referencia_capacidade=True,
        )
        self.assertEqual(category.aliases, ['scanner', 'scanners industriais'])

        with self.assertRaises(ValidationError):
            CategoriaEquipamentoEmpresa.objects.create(
                empresa=self.empresa,
                nome='Outra referência',
                referencia_capacidade=True,
            )
        with self.assertRaises(ValidationError):
            CategoriaEquipamentoEmpresa.objects.create(
                empresa=self.outra_empresa,
                nome='Aliases inválidos',
                aliases='não é uma lista',
            )

    def test_documentation_section_defaults_to_disabled_and_falls_back_to_label(self):
        section = SecaoDocumentacaoEmpresa.objects.create(
            empresa=self.empresa,
            codigo=SecaoDocumentacaoEmpresa.Codigo.MANUAIS,
        )

        self.assertFalse(section.habilitado)
        self.assertEqual(section.nome_apresentacao, 'Manuais de equipamentos')

        section.nome_exibicao = 'Manual Operacional'
        self.assertEqual(section.nome_apresentacao, 'Manual Operacional')


class ExistingTenantConfigurationDataMigrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inventory_companies = (
            Empresa.objects.create(
                nome='Inventory Brasil',
                slug='inventory-brasil',
            ),
            Empresa.objects.create(
                nome='Inventory Latam',
                slug='inventory-latam',
            ),
            Empresa.objects.create(
                nome='OXXO',
                slug='oxxo',
            ),
        )
        cls.external = Empresa.objects.create(nome='Tenant industrial')
        Produto.objects.create(
            codigo='LEGADO-CONFIG-001',
            descricao='Produto legado do grupo',
            fabricante='Inventory',
            modelo='Legado',
            categoria='Categoria legada adicional',
        )
        Produto.objects.create(
            codigo='EXTERNO-CONFIG-001',
            descricao='Produto industrial próprio',
            fabricante='Industrial',
            modelo='Próprio',
            categoria='Máquinas industriais',
            empresa_catalogo_origem=cls.external,
        )

    def test_data_migration_preserves_inventory_without_configuring_external_tenant(self):
        migration = import_module(
            'estoque.migrations.0052_tenant_configuration_foundations'
        )
        schema_editor = SimpleNamespace(connection=connection)

        migration.seed_existing_tenant_configuration(apps, schema_editor)

        expected_inventory_categories = {
            'Coletores',
            'Impressoras',
            'Notebooks',
            'Routers',
            'Categoria legada adicional',
        }
        for company in self.inventory_companies:
            with self.subTest(company=company.nome):
                self.assertEqual(
                    set(company.categorias_equipamento.values_list('nome', flat=True)),
                    expected_inventory_categories,
                )
                self.assertEqual(
                    set(
                        company.secoes_documentacao.filter(
                            habilitado=True,
                        ).values_list('codigo', flat=True)
                    ),
                    set(migration.DOCUMENTATION_SECTIONS),
                )

        self.assertEqual(
            set(self.external.categorias_equipamento.values_list('nome', flat=True)),
            {'Máquinas industriais'},
        )
        self.assertFalse(self.external.secoes_documentacao.exists())
        self.assertFalse(TermoEmpresa.objects.exists())

    def test_checklist_rules_are_seeded_only_for_inventory_group(self):
        foundation = import_module(
            'estoque.migrations.0052_tenant_configuration_foundations'
        )
        checklist_rules = import_module(
            'estoque.migrations.0056_categorias_checklist_configuraveis'
        )
        schema_editor = SimpleNamespace(connection=connection)
        foundation.seed_existing_tenant_configuration(apps, schema_editor)
        checklist_rules.preserve_inventory_rules(apps, schema_editor)

        for company in self.inventory_companies:
            collector = company.categorias_equipamento.get(nome='Coletores')
            self.assertEqual(collector.limite_checklist_por_pessoas, 5)
            self.assertTrue(collector.referencia_capacidade)
            self.assertIn('coletores', collector.aliases)

        external_category = self.external.categorias_equipamento.get(
            nome='Máquinas industriais'
        )
        self.assertIsNone(external_category.limite_checklist_por_pessoas)
        self.assertFalse(external_category.referencia_capacidade)
        self.assertEqual(external_category.aliases, [])
