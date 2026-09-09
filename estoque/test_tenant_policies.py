from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from estoque.decorators import (
    tenant_company_access,
    tenant_object_access,
    tenant_required,
)
from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Perfil,
    RelacionamentoEmpresa,
)
from estoque.tenant_policies import TenantAccessPolicy
from estoque.tenant_scope import TenantScope


class TenantAccessPolicyTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.brasil = Empresa.objects.create(nome='Inventory Brasil policy')
        self.latam = Empresa.objects.create(nome='Inventory LATAM policy')
        self.oxxo = Empresa.objects.create(nome='OXXO policy')
        self.externa = Empresa.objects.create(nome='Empresa externa policy')

        self.latam_relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.brasil,
            empresa_destino=self.latam,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=self.latam_relationship,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            acao=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
        )
        self.oxxo_relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.brasil,
            empresa_destino=self.oxxo,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=self.oxxo_relationship,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.OPERACAO,
            acao=CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR,
        )

        self.admin = self._user('policy.admin', Perfil.Role.ADMIN, self.brasil)
        self.admin.perfil.empresas_acesso_adicional.add(self.latam)
        self.admin_without_latam = self._user(
            'policy.admin.restrito', Perfil.Role.ADMIN, self.brasil
        )
        self.gestor = self._user('policy.gestor', Perfil.Role.GESTOR, self.brasil)
        self.legacy_admin = self._user(
            'policy.admin.sem.empresa', Perfil.Role.ADMIN, None
        )
        self.superuser = User.objects.create_superuser(
            'policy.superuser', password='SenhaTeste123!'
        )

        self.base_brasil = Base.objects.create(
            nome='Base Brasil policy', empresa=self.brasil
        )
        self.base_latam = Base.objects.create(
            nome='Base LATAM policy', empresa=self.latam
        )
        self.base_externa = Base.objects.create(
            nome='Base externa policy', empresa=self.externa
        )

    @staticmethod
    def _user(username, role, company):
        user = User.objects.create_user(username, password='SenhaTeste123!')
        user.perfil.role = role
        user.perfil.empresa = company
        user.perfil.save()
        return user

    def request_for(self, user):
        request = self.factory.get('/')
        request.user = user
        request.tenant_scope = TenantScope.for_user(user)
        return request

    def test_policy_allows_primary_and_only_selected_related_company(self):
        request = self.request_for(self.admin)

        self.assertTrue(TenantAccessPolicy.can_access_company(request, self.brasil))
        self.assertTrue(TenantAccessPolicy.can_access_company(request, self.latam))
        self.assertFalse(TenantAccessPolicy.can_access_company(request, self.oxxo))
        self.assertFalse(TenantAccessPolicy.can_access_company(request, self.externa))

    def test_related_capability_must_match_resource_and_action(self):
        request = self.request_for(self.admin)

        self.assertTrue(TenantAccessPolicy.can_access_company(
            request,
            self.latam,
            resource=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            action=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
        ))
        self.assertFalse(TenantAccessPolicy.can_access_company(
            request,
            self.latam,
            resource=CapacidadeRelacionamentoEmpresa.Recurso.ESTOQUE,
            action=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
        ))

    def test_gestor_does_not_inherit_company_relationships(self):
        request = self.request_for(self.gestor)

        self.assertTrue(TenantAccessPolicy.can_access_company(request, self.brasil))
        self.assertFalse(TenantAccessPolicy.can_access_company(
            request, self.brasil, manage=True
        ))
        self.assertFalse(TenantAccessPolicy.can_access_company(request, self.latam))

    def test_superuser_has_explicit_platform_scope_without_company(self):
        request = self.request_for(self.superuser)

        self.assertTrue(TenantAccessPolicy.can_access_company(request, self.externa))
        self.assertTrue(TenantAccessPolicy.require_tenant(request).is_platform_scope)

    def test_foreign_scope_on_request_is_never_trusted(self):
        request = self.request_for(self.admin_without_latam)
        request.tenant_scope = TenantScope.for_user(self.admin)

        self.assertFalse(TenantAccessPolicy.can_access_company(request, self.latam))

    def test_tenant_required_denies_anonymous_and_profile_without_company(self):
        protected = tenant_required(lambda request: HttpResponse('ok'))
        anonymous_request = self.factory.get('/')
        anonymous_request.user = AnonymousUser()

        with self.assertRaises(PermissionDenied):
            protected(anonymous_request)
        with self.assertRaises(PermissionDenied):
            protected(self.request_for(self.legacy_admin))

    def test_tenant_required_allows_fixed_tenant_and_superuser(self):
        protected = tenant_required(lambda request: HttpResponse('ok'))

        self.assertEqual(protected(self.request_for(self.admin)).status_code, 200)
        self.assertEqual(
            protected(self.request_for(self.superuser)).status_code,
            200,
        )

    def test_company_decorator_enforces_selected_relationship_and_capability(self):
        @tenant_company_access(
            resource=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            action=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
        )
        def protected(request, empresa_id):
            return HttpResponse(request.tenant_company.nome)

        allowed = protected(self.request_for(self.admin), empresa_id=self.latam.pk)
        self.assertContains(allowed, self.latam.nome)

        with self.assertRaises(PermissionDenied):
            protected(self.request_for(self.admin), empresa_id=self.oxxo.pk)
        with self.assertRaises(PermissionDenied):
            protected(
                self.request_for(self.admin_without_latam),
                empresa_id=self.latam.pk,
            )

    def test_manage_mode_requires_operational_admin_capability_on_related(self):
        self.admin.perfil.empresas_acesso_adicional.add(self.oxxo)
        request = self.request_for(self.admin)

        self.assertFalse(TenantAccessPolicy.can_access_company(
            request, self.latam, manage=True
        ))
        self.assertTrue(TenantAccessPolicy.can_access_company(
            request, self.oxxo, manage=True
        ))

    def test_object_decorator_blocks_cross_tenant_reference(self):
        @tenant_object_access(Base, company_path='empresa', lookup_url_kwarg='base_id')
        def protected(request, base_id):
            return HttpResponse(request.tenant_object.nome)

        allowed = protected(
            self.request_for(self.admin), base_id=self.base_brasil.pk
        )
        self.assertContains(allowed, self.base_brasil.nome)

        related = protected(
            self.request_for(self.admin), base_id=self.base_latam.pk
        )
        self.assertContains(related, self.base_latam.nome)

        with self.assertRaises(PermissionDenied):
            protected(
                self.request_for(self.admin), base_id=self.base_externa.pk
            )

    def test_invalid_decorator_configuration_fails_explicitly(self):
        with self.assertRaises(ImproperlyConfigured):
            tenant_company_access(resource='ESTOQUE')
        with self.assertRaises(ImproperlyConfigured):
            tenant_object_access(Base, company_path='')
