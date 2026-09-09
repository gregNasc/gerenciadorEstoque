from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase

from estoque.models import (
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Perfil,
    RelacionamentoEmpresa,
)
from estoque.tenant_context import TenantRequestContext
from estoque.tenant_scope import TenantScope


class TenantScopeTests(TestCase):
    def setUp(self):
        self.company_a = Empresa.objects.create(nome='Empresa Scope A')
        self.company_b = Empresa.objects.create(nome='Empresa Scope B')

    @staticmethod
    def _user(username, *, role=Perfil.Role.OPERADOR, company=None, superuser=False):
        user = User.objects.create_user(username=username, password='senha-de-teste')
        user.is_superuser = superuser
        user.is_staff = superuser
        user.save(update_fields=['is_superuser', 'is_staff'])
        profile = user.perfil
        profile.role = role
        profile.empresa = company
        profile.save()
        return user

    def test_anonymous_scope_is_empty(self):
        scope = TenantScope.for_user(AnonymousUser())

        self.assertTrue(scope.is_empty)
        self.assertFalse(scope.is_platform_scope)
        self.assertFalse(scope.visible_companies().exists())
        self.assertFalse(scope.can_view_company(self.company_a))
        self.assertFalse(scope.can_manage_company(self.company_a))

    def test_superuser_has_explicit_global_view_and_management(self):
        user = self._user('scope.superuser', superuser=True)

        scope = TenantScope.for_user(user)

        self.assertTrue(scope.is_platform_scope)
        self.assertFalse(scope.is_empty)
        self.assertEqual(
            set(scope.visible_companies().values_list('pk', flat=True)),
            {self.company_a.pk, self.company_b.pk},
        )
        self.assertTrue(scope.can_view_company(self.company_b))
        self.assertTrue(scope.can_manage_company(self.company_b))

    def test_admin_can_view_and_manage_only_primary_company(self):
        user = self._user(
            'scope.admin',
            role=Perfil.Role.ADMIN,
            company=self.company_a,
        )

        scope = TenantScope.for_user(user)

        self.assertEqual(scope.primary_company, self.company_a)
        self.assertEqual(list(scope.visible_companies()), [self.company_a])
        self.assertTrue(scope.can_view_company(self.company_a))
        self.assertTrue(scope.can_manage_company(self.company_a.pk))
        self.assertFalse(scope.can_view_company(self.company_b))
        self.assertFalse(scope.can_manage_company(self.company_b))

    def test_gestor_views_primary_but_does_not_administer_company(self):
        user = self._user(
            'scope.gestor',
            role=Perfil.Role.GESTOR,
            company=self.company_a,
        )

        scope = TenantScope.for_user(user)

        self.assertTrue(scope.can_view_company(self.company_a))
        self.assertFalse(scope.can_manage_company(self.company_a))
        self.assertFalse(scope.can_view_company(self.company_b))

    def test_explicit_related_company_adds_view_but_not_implicit_management(self):
        user = self._user(
            'scope.admin.related',
            role=Perfil.Role.ADMIN,
            company=self.company_a,
        )
        context = TenantRequestContext.from_profile(
            user,
            user.perfil,
            related_tenant_ids=(self.company_b.pk,),
        )
        relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a,
            empresa_destino=self.company_b,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relationship,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            acao=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
        )

        scope = TenantScope.for_user(user, context=context)

        self.assertEqual(
            set(scope.visible_companies().values_list('pk', flat=True)),
            {self.company_a.pk, self.company_b.pk},
        )
        self.assertTrue(scope.can_view_company(self.company_b))
        self.assertFalse(scope.can_manage_company(self.company_b))
        self.assertTrue(scope.can_manage_company(self.company_a))

    def test_inventory_organization_is_directional_when_explicitly_resolved(self):
        inventory_brasil = Empresa.objects.create(nome='Inventory Brasil Scope')
        inventory_latam = Empresa.objects.create(nome='Inventory Latam Scope')
        oxxo = Empresa.objects.create(nome='OXXO Scope')
        unrelated = Empresa.objects.create(nome='Empresa Sem Relacao Scope')
        admin_brasil = self._user(
            'scope.inventory.brasil',
            role=Perfil.Role.ADMIN,
            company=inventory_brasil,
        )
        admin_latam = self._user(
            'scope.inventory.latam',
            role=Perfil.Role.ADMIN,
            company=inventory_latam,
        )
        admin_oxxo = self._user(
            'scope.oxxo',
            role=Perfil.Role.ADMIN,
            company=oxxo,
        )
        brasil_context = TenantRequestContext.from_profile(
            admin_brasil,
            admin_brasil.perfil,
            related_tenant_ids=(inventory_latam.pk, oxxo.pk),
        )
        for destination in (inventory_latam, oxxo):
            relationship = RelacionamentoEmpresa.objects.create(
                empresa_origem=inventory_brasil,
                empresa_destino=destination,
            )
            CapacidadeRelacionamentoEmpresa.objects.create(
                relacionamento=relationship,
                recurso=CapacidadeRelacionamentoEmpresa.Recurso.OPERACAO,
                acao=CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR,
            )

        brasil_scope = TenantScope.for_user(admin_brasil, context=brasil_context)
        latam_scope = TenantScope.for_user(admin_latam)
        oxxo_scope = TenantScope.for_user(admin_oxxo)

        self.assertEqual(
            set(brasil_scope.visible_companies().values_list('pk', flat=True)),
            {inventory_brasil.pk, inventory_latam.pk, oxxo.pk},
        )
        self.assertFalse(brasil_scope.can_view_company(unrelated))
        self.assertEqual(
            set(latam_scope.visible_companies().values_list('pk', flat=True)),
            {inventory_latam.pk},
        )
        self.assertEqual(
            set(oxxo_scope.visible_companies().values_list('pk', flat=True)),
            {oxxo.pk},
        )

    def test_context_from_another_user_is_ignored(self):
        user_a = self._user(
            'scope.user.a',
            role=Perfil.Role.ADMIN,
            company=self.company_a,
        )
        user_b = self._user(
            'scope.user.b',
            role=Perfil.Role.ADMIN,
            company=self.company_b,
        )
        forged_context = TenantRequestContext.from_profile(user_b, user_b.perfil)

        scope = TenantScope.for_user(user_a, context=forged_context)

        self.assertTrue(scope.is_empty)
        self.assertIsNone(scope.primary_company)
        self.assertFalse(scope.can_view_company(self.company_a))
        self.assertFalse(scope.can_view_company(self.company_b))

    def test_admin_without_company_has_no_visible_or_manageable_fallback(self):
        user = self._user('scope.admin.legacy', role=Perfil.Role.ADMIN)

        scope = TenantScope.for_user(user)

        self.assertTrue(scope.is_empty)
        self.assertFalse(scope.visible_companies().exists())
        self.assertFalse(scope.can_view_company(self.company_a))
        self.assertFalse(scope.can_manage_company(self.company_a))

    def test_user_without_profile_fails_closed(self):
        user = self._user('scope.sem.perfil', company=self.company_a)
        user.perfil.delete()

        scope = TenantScope.for_user(user)

        self.assertTrue(scope.is_empty)
        self.assertIsNone(scope.primary_company)

    def test_invalid_company_reference_is_denied(self):
        user = self._user(
            'scope.invalid.company',
            role=Perfil.Role.ADMIN,
            company=self.company_a,
        )
        scope = TenantScope.for_user(user)

        self.assertFalse(scope.can_view_company(None))
        self.assertFalse(scope.can_view_company('nao-e-id'))
        self.assertFalse(scope.can_manage_company(None))
