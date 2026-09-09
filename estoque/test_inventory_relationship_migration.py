from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import TestCase

from estoque.models import (
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Perfil,
    RelacionamentoEmpresa,
)
from estoque.tenant_scope import TenantScope


migration = import_module(
    'estoque.migrations.0045_inventory_brasil_relationships'
)


class InventoryBrasilRelationshipMigrationTests(TestCase):
    @staticmethod
    def _run_migration():
        migration.create_inventory_brasil_relationships(django_apps, None)

    @staticmethod
    def _companies():
        return {
            'brasil': Empresa.objects.create(
                nome='Inventory Brasil', slug='inventory-brasil'
            ),
            'latam': Empresa.objects.create(
                nome='Inventory Latam', slug='inventory-latam'
            ),
            'oxxo': Empresa.objects.create(nome='OXXO', slug='oxxo'),
            'other': Empresa.objects.create(
                nome='Empresa sem relação', slug='empresa-sem-relacao'
            ),
        }

    def test_empty_database_is_valid_for_fresh_installation(self):
        self._run_migration()

        self.assertFalse(RelacionamentoEmpresa.objects.exists())
        self.assertFalse(CapacidadeRelacionamentoEmpresa.objects.exists())

    def test_partial_organization_fails_before_writing(self):
        Empresa.objects.create(nome='Inventory Brasil', slug='inventory-brasil')

        with self.assertRaisesRegex(RuntimeError, 'Correspondências'):
            self._run_migration()

        self.assertFalse(RelacionamentoEmpresa.objects.exists())

    def test_ambiguous_company_fails_before_writing(self):
        self._companies()
        Empresa.objects.create(
            nome='Outra empresa com slug conflitante',
            slug='inventory-brasil',
        )

        with self.assertRaisesRegex(RuntimeError, 'Correspondências'):
            self._run_migration()

        self.assertFalse(RelacionamentoEmpresa.objects.exists())

    def test_creates_only_directional_full_operational_relationships(self):
        companies = self._companies()

        self._run_migration()

        relationships = RelacionamentoEmpresa.objects.filter(
            empresa_origem=companies['brasil'],
            ativo=True,
        )
        self.assertEqual(
            set(relationships.values_list('empresa_destino_id', flat=True)),
            {companies['latam'].pk, companies['oxxo'].pk},
        )
        self.assertFalse(RelacionamentoEmpresa.objects.filter(
            empresa_origem__in=(companies['latam'], companies['oxxo']),
            empresa_destino=companies['brasil'],
        ).exists())
        self.assertFalse(RelacionamentoEmpresa.objects.filter(
            empresa_destino=companies['other'],
        ).exists())

        expected_count = len(migration.FULL_OPERATIONAL_CAPABILITIES)
        for relationship in relationships:
            self.assertEqual(
                relationship.capacidades.filter(ativo=True).count(),
                expected_count,
            )
            self.assertTrue(relationship.capacidades.filter(
                recurso='OPERACAO',
                acao='ADMINISTRAR',
                ativo=True,
            ).exists())

    def test_migration_is_idempotent_and_reactivates_required_records(self):
        companies = self._companies()
        self._run_migration()
        relationship = RelacionamentoEmpresa.objects.get(
            empresa_origem=companies['brasil'],
            empresa_destino=companies['latam'],
        )
        capability = relationship.capacidades.get(
            recurso='CHAMADOS',
            acao='VISUALIZAR',
        )
        relationship.ativo = False
        relationship.save(update_fields=['ativo'])
        capability.ativo = False
        capability.save(update_fields=['ativo'])
        initial_relationships = RelacionamentoEmpresa.objects.count()
        initial_capabilities = CapacidadeRelacionamentoEmpresa.objects.count()

        self._run_migration()

        relationship.refresh_from_db()
        capability.refresh_from_db()
        self.assertTrue(relationship.ativo)
        self.assertTrue(capability.ativo)
        self.assertEqual(RelacionamentoEmpresa.objects.count(), initial_relationships)
        self.assertEqual(
            CapacidadeRelacionamentoEmpresa.objects.count(),
            initial_capabilities,
        )

    def test_tenant_scope_uses_persisted_relations_without_name_rules(self):
        companies = self._companies()
        self._run_migration()
        admin_brasil = User.objects.create_user(
            username='migration.admin.brasil',
            password='senha-de-teste',
        )
        admin_brasil.perfil.role = Perfil.Role.ADMIN
        admin_brasil.perfil.empresa = companies['brasil']
        admin_brasil.perfil.save()
        admin_brasil.perfil.empresas_acesso_adicional.add(
            companies['latam'], companies['oxxo']
        )
        admin_latam = User.objects.create_user(
            username='migration.admin.latam',
            password='senha-de-teste',
        )
        admin_latam.perfil.role = Perfil.Role.ADMIN
        admin_latam.perfil.empresa = companies['latam']
        admin_latam.perfil.save()

        brasil_scope = TenantScope.for_user(admin_brasil)
        latam_scope = TenantScope.for_user(admin_latam)

        self.assertEqual(
            set(brasil_scope.visible_companies().values_list('pk', flat=True)),
            {companies['brasil'].pk, companies['latam'].pk, companies['oxxo'].pk},
        )
        self.assertTrue(brasil_scope.can_manage_company(companies['latam']))
        self.assertTrue(brasil_scope.can_manage_company(companies['oxxo']))
        self.assertFalse(brasil_scope.can_view_company(companies['other']))
        self.assertEqual(
            set(latam_scope.visible_companies().values_list('pk', flat=True)),
            {companies['latam'].pk},
        )
        self.assertFalse(latam_scope.can_view_company(companies['brasil']))
