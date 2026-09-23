from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from estoque.models import Empresa, Modulo, ModuloEmpresa
from estoque.tenant_features import TenantFeatureService


class TenantFeatureStage21Tests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser_features_21',
            email='superuser-features-21@example.test',
            password='senha-apenas-teste-21',
        )
        self.admin = User.objects.create_user('admin_features_21')
        self.company_a = Empresa.objects.create(
            nome='Empresa Features A',
            slug='empresa-features-a',
        )
        self.company_b = Empresa.objects.create(
            nome='Empresa Features B',
            slug='empresa-features-b',
        )

    def test_catalog_contains_the_stage_21_modules(self):
        self.assertEqual(
            set(Modulo.objects.values_list('codigo', flat=True)),
            set(Modulo.Codigo.values),
        )

    def test_new_company_starts_with_every_module_disabled(self):
        company = Empresa.objects.create(
            nome='Empresa Features Inativa',
            slug='empresa-features-inativa',
            ativa=False,
        )
        self.assertEqual(
            company.modulos_configurados.filter(habilitado=True).count(),
            0,
        )
        self.assertEqual(
            TenantFeatureService.enabled_features(company),
            frozenset(),
        )

    def test_feature_can_be_disabled_for_only_one_tenant(self):
        TenantFeatureService.configure(
            tenant=self.company_b,
            codigo=Modulo.Codigo.CHAMADOS,
            enabled=True,
            actor=self.superuser,
        )
        configuration = TenantFeatureService.configure(
            tenant=self.company_a,
            codigo=Modulo.Codigo.CHAMADOS,
            enabled=False,
            actor=self.superuser,
        )

        self.assertEqual(configuration.configurado_por, self.superuser)
        self.assertFalse(self.company_a.has_feature(Modulo.Codigo.CHAMADOS))
        self.assertTrue(self.company_b.has_feature(Modulo.Codigo.CHAMADOS))

    def test_default_provisioning_is_idempotent_and_preserves_configuration(self):
        TenantFeatureService.configure(
            tenant=self.company_a,
            codigo=Modulo.Codigo.TORY,
            enabled=True,
            actor=self.superuser,
        )

        self.assertEqual(TenantFeatureService.provision_defaults(self.company_a), 0)
        self.assertTrue(self.company_a.has_feature(Modulo.Codigo.TORY))

    def test_only_superuser_can_configure_features(self):
        with self.assertRaises(PermissionDenied):
            TenantFeatureService.configure(
                tenant=self.company_a,
                codigo=Modulo.Codigo.TORY,
                enabled=False,
                actor=self.admin,
            )

    def test_unknown_feature_and_missing_assignment_fail_closed(self):
        self.assertFalse(self.company_a.has_feature('nao-existe'))
        ModuloEmpresa.objects.filter(
            empresa=self.company_a,
            modulo__codigo=Modulo.Codigo.ESTOQUE,
        ).delete()
        self.assertFalse(self.company_a.has_feature(Modulo.Codigo.ESTOQUE))

        with self.assertRaises(ValidationError):
            TenantFeatureService.configure(
                tenant=self.company_a,
                codigo='nao-existe',
                enabled=True,
                actor=self.superuser,
            )

    def test_inactive_company_or_platform_module_is_not_effectively_enabled(self):
        self.company_a.ativa = False
        self.company_a.save(update_fields=('ativa', 'atualizado_em'))
        self.assertFalse(self.company_a.has_feature(Modulo.Codigo.INSUMOS))

        self.company_a.ativa = True
        self.company_a.save(update_fields=('ativa', 'atualizado_em'))
        Modulo.objects.filter(codigo=Modulo.Codigo.INSUMOS).update(ativo=False)
        self.assertFalse(self.company_a.has_feature(Modulo.Codigo.INSUMOS))

    def test_company_module_pair_is_unique(self):
        module = Modulo.objects.get(codigo=Modulo.Codigo.CATALOGO)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModuloEmpresa.objects.create(
                empresa=self.company_a,
                modulo=module,
                habilitado=True,
            )
