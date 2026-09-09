from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from estoque.models import (
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Perfil,
    RelacionamentoEmpresa,
)
from estoque.tenant_scope import TenantScope


backfill_migration = import_module(
    'estoque.migrations.0046_perfil_empresas_acesso_adicional'
)


class AdminAdditionalCompanyBackfillTests(TestCase):
    def test_backfill_preserves_existing_related_access_for_admins_only(self):
        origin = Empresa.objects.create(nome='Backfill origem')
        destination = Empresa.objects.create(nome='Backfill destino')
        inactive_destination = Empresa.objects.create(nome='Backfill inativo')
        relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=origin,
            empresa_destino=destination,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relationship,
            recurso='CHAMADOS',
            acao='VISUALIZAR',
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relationship,
            recurso='ESTOQUE',
            acao='VISUALIZAR',
        )
        inactive_relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=origin,
            empresa_destino=inactive_destination,
            ativo=False,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=inactive_relationship,
            recurso='ESTOQUE',
            acao='VISUALIZAR',
        )
        admin_user = User.objects.create_user('backfill.admin')
        admin_user.perfil.role = Perfil.Role.ADMIN
        admin_user.perfil.empresa = origin
        admin_user.perfil.save()
        gestor = User.objects.create_user('backfill.gestor')
        gestor.perfil.role = Perfil.Role.GESTOR
        gestor.perfil.empresa = origin
        gestor.perfil.save()

        self.assertEqual(
            backfill_migration._active_destination_ids(
                CapacidadeRelacionamentoEmpresa,
                origin.pk,
            ),
            [destination.pk],
        )

        backfill_migration.preserve_existing_admin_relationship_access(
            django_apps, None
        )
        backfill_migration.preserve_existing_admin_relationship_access(
            django_apps, None
        )

        self.assertEqual(
            list(admin_user.perfil.empresas_acesso_adicional.all()),
            [destination],
        )
        self.assertFalse(gestor.perfil.empresas_acesso_adicional.exists())


class AdminMultiCompanyUserManagementTests(TestCase):
    def setUp(self):
        self.primary = Empresa.objects.create(nome='Inventory principal teste')
        self.latam = Empresa.objects.create(nome='Inventory Latam teste')
        self.oxxo = Empresa.objects.create(nome='OXXO teste')
        self.unrelated = Empresa.objects.create(nome='Empresa sem relação teste')
        for destination in (self.latam, self.oxxo):
            relationship = RelacionamentoEmpresa.objects.create(
                empresa_origem=self.primary,
                empresa_destino=destination,
            )
            CapacidadeRelacionamentoEmpresa.objects.create(
                relacionamento=relationship,
                recurso='OPERACAO',
                acao='ADMINISTRAR',
            )
        self.creator = User.objects.create_user(
            'multiempresa.admin.criador',
            password='SenhaDeTeste123!',
        )
        self.creator.perfil.role = Perfil.Role.ADMIN
        self.creator.perfil.empresa = self.primary
        self.creator.perfil.save()
        self.client.force_login(self.creator)
        self.url = reverse('estoque:cadastrar_usuario')

    def _post_data(self, **overrides):
        data = {
            'username': 'multiempresa.admin.alvo',
            'password': 'SenhaOriginal123!',
            'first_name': 'Admin',
            'last_name': 'Multiempresa',
            'email': 'multiempresa@example.test',
            'perfil_acesso': 'admin',
            'empresa': str(self.primary.pk),
            'is_active': 'on',
        }
        data.update(overrides)
        return data

    def test_admin_can_be_created_with_one_related_company(self):
        response = self.client.post(
            self.url,
            self._post_data(empresas_acesso_adicional=[str(self.oxxo.pk)]),
        )

        self.assertRedirects(response, self.url)
        user = User.objects.get(username='multiempresa.admin.alvo')
        self.assertEqual(
            list(user.perfil.empresas_acesso_adicional.all()),
            [self.oxxo],
        )
        self.assertEqual(
            set(TenantScope.for_user(user).visible_companies()),
            {self.primary, self.oxxo},
        )

    def test_admin_can_be_created_with_both_related_companies(self):
        self.client.post(
            self.url,
            self._post_data(empresas_acesso_adicional=[
                str(self.latam.pk), str(self.oxxo.pk),
            ]),
        )

        user = User.objects.get(username='multiempresa.admin.alvo')
        self.assertEqual(
            set(user.perfil.empresas_acesso_adicional.all()),
            {self.latam, self.oxxo},
        )
        self.assertEqual(
            set(TenantScope.for_user(user).visible_companies()),
            {self.primary, self.latam, self.oxxo},
        )

    def test_unrelated_company_is_rejected(self):
        response = self.client.post(
            self.url,
            self._post_data(
                username='multiempresa.admin.invalido',
                empresas_acesso_adicional=[str(self.unrelated.pk)],
            ),
        )

        self.assertRedirects(response, self.url)
        self.assertFalse(
            User.objects.filter(username='multiempresa.admin.invalido').exists()
        )

    def test_edit_can_reduce_scope_without_changing_password(self):
        target = User.objects.create_user(
            'multiempresa.admin.editar',
            password='SenhaPreservada123!',
            email='editar@example.test',
        )
        target.perfil.role = Perfil.Role.ADMIN
        target.perfil.empresa = self.primary
        target.perfil.save()
        target.perfil.empresas_acesso_adicional.add(self.latam, self.oxxo)
        password_hash = target.password

        response = self.client.post(
            self.url,
            self._post_data(
                usuario_id=str(target.pk),
                username=target.username,
                password='',
                email=target.email,
                empresas_acesso_adicional=[str(self.latam.pk)],
            ),
        )

        self.assertRedirects(response, self.url)
        target.refresh_from_db()
        self.assertEqual(target.password, password_hash)
        self.assertTrue(target.check_password('SenhaPreservada123!'))
        self.assertEqual(
            list(target.perfil.empresas_acesso_adicional.all()),
            [self.latam],
        )

    def test_user_screen_exposes_only_configured_relationship_options(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Empresas adicionais do Admin')
        self.assertContains(response, f'data-origem="{self.primary.pk}"', count=2)
        self.assertContains(response, f'value="{self.latam.pk}"')
        self.assertContains(response, f'value="{self.oxxo.pk}"')
        self.assertNotContains(
            response,
            f'name="empresas_acesso_adicional" value="{self.unrelated.pk}"',
        )
