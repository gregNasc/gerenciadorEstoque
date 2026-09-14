from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.db import DatabaseError
from django.test import RequestFactory, TestCase

from estoque.middleware import EmpresaMiddleware
from estoque.models import Empresa, Perfil
from estoque.tenant_context import TenantRequestContext


class EmpresaMiddlewareTenantContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.empresa = Empresa.objects.create(nome='Tenant Contexto')

    def _execute(self, user):
        request = self.factory.get('/')
        request.user = user
        return EmpresaMiddleware(lambda current_request: current_request)(request)

    def _user(self, username, *, role=Perfil.Role.ADMIN, empresa=None, superuser=False):
        user = User.objects.create_user(username=username, password='senha-de-teste')
        user.is_superuser = superuser
        user.is_staff = superuser
        user.save(update_fields=['is_superuser', 'is_staff'])
        profile = user.perfil
        profile.role = role
        profile.empresa = empresa
        profile.save()
        return user

    def test_authenticated_user_exposes_canonical_tenant_context(self):
        user = self._user('admin.tenant', empresa=self.empresa)

        request = self._execute(user)

        self.assertEqual(request.tenant, self.empresa)
        self.assertFalse(hasattr(request, 'empresa'))
        self.assertEqual(request.tenant_scope.primary_tenant_id, self.empresa.pk)
        self.assertEqual(request.tenant_scope.tenant_ids, {self.empresa.pk})
        self.assertTrue(request.tenant_scope.has_fixed_tenant)
        self.assertFalse(request.tenant_scope.is_platform_superuser)
        self.assertEqual(request.tenant_context.user_id, user.pk)
        self.assertEqual(request.tenant_context.profile_role, Perfil.Role.ADMIN)

    def test_anonymous_request_receives_empty_context(self):
        request = self._execute(AnonymousUser())

        self.assertIsNone(request.tenant)
        self.assertFalse(hasattr(request, 'empresa'))
        self.assertTrue(request.tenant_scope.is_empty)
        self.assertFalse(request.tenant_scope.is_platform_superuser)
        self.assertTrue(request.tenant_context.is_empty)

    def test_legacy_admin_without_company_does_not_receive_global_fallback(self):
        user = self._user('admin.legado.sem.tenant')

        request = self._execute(user)

        self.assertIsNone(request.tenant)
        self.assertEqual(request.tenant_scope.tenant_ids, frozenset())
        self.assertTrue(request.tenant_scope.is_empty)
        self.assertFalse(request.tenant_scope.is_platform_superuser)

    def test_superuser_may_have_no_fixed_tenant_without_implicit_scope(self):
        user = self._user('superuser.contexto', superuser=True)

        request = self._execute(user)

        self.assertIsNone(request.tenant)
        self.assertTrue(request.tenant_scope.is_platform_superuser)
        self.assertEqual(request.tenant_scope.tenant_ids, frozenset())
        self.assertFalse(request.tenant_scope.is_empty)
        self.assertTrue(request.tenant_context.is_empty)

    def test_database_error_fails_closed(self):
        user = self._user('admin.erro.banco', empresa=self.empresa)

        with patch(
            'estoque.middleware.Perfil.objects.select_related',
            side_effect=DatabaseError('falha simulada'),
        ):
            request = self._execute(user)

        self.assertIsNone(request.tenant)
        self.assertFalse(hasattr(request, 'empresa'))
        self.assertTrue(request.tenant_scope.is_empty)

    def test_context_can_represent_explicit_related_tenants(self):
        user = self._user('admin.relacionado', empresa=self.empresa)
        related = Empresa.objects.create(nome='Tenant Relacionado')

        context = TenantRequestContext.from_profile(
            user,
            user.perfil,
            related_tenant_ids=[self.empresa.pk, related.pk, related.pk],
        )

        self.assertEqual(context.primary_tenant, self.empresa)
        self.assertEqual(context.related_tenant_ids, {related.pk})
        self.assertEqual(context.tenant_ids, {self.empresa.pk, related.pk})

    def test_context_does_not_offer_write_authorization_api(self):
        user = self._user('admin.sem.policy', empresa=self.empresa)
        context = TenantRequestContext.from_profile(user, user.perfil)

        self.assertFalse(hasattr(context, 'can_manage'))
        self.assertFalse(hasattr(context, 'can_write'))
        self.assertFalse(hasattr(context, 'can_view'))
