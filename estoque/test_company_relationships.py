from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from estoque.models import (
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Perfil,
    RelacionamentoEmpresa,
)
from estoque.tenant_scope import TenantScope


class CompanyRelationshipModelTests(TestCase):
    def setUp(self):
        self.company_a = Empresa.objects.create(nome='Relacionamento A')
        self.company_b = Empresa.objects.create(nome='Relacionamento B')

    def _relationship(self, **kwargs):
        values = {
            'empresa_origem': self.company_a,
            'empresa_destino': self.company_b,
        }
        values.update(kwargs)
        return RelacionamentoEmpresa.objects.create(**values)

    def test_relationship_is_directional(self):
        relationship = self._relationship()

        self.assertEqual(
            list(self.company_a.relacionamentos_saida.all()),
            [relationship],
        )
        self.assertEqual(
            list(self.company_b.relacionamentos_entrada.all()),
            [relationship],
        )
        self.assertFalse(
            RelacionamentoEmpresa.objects.filter(
                empresa_origem=self.company_b,
                empresa_destino=self.company_a,
            ).exists()
        )

    def test_relationship_rejects_same_origin_and_destination(self):
        relationship = RelacionamentoEmpresa(
            empresa_origem=self.company_a,
            empresa_destino=self.company_a,
        )

        with self.assertRaises(ValidationError):
            relationship.full_clean()

        with self.assertRaises(IntegrityError), transaction.atomic():
            relationship.save()

    def test_directional_pair_is_unique(self):
        self._relationship()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self._relationship()

    def test_capability_is_unique_per_resource_and_action(self):
        relationship = self._relationship()
        values = {
            'relacionamento': relationship,
            'recurso': CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            'acao': CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
        }
        CapacidadeRelacionamentoEmpresa.objects.create(**values)

        with self.assertRaises(IntegrityError), transaction.atomic():
            CapacidadeRelacionamentoEmpresa.objects.create(**values)

    def test_capability_catalog_covers_mapped_resources_and_actions(self):
        resources = set(CapacidadeRelacionamentoEmpresa.Recurso.values)
        actions = set(CapacidadeRelacionamentoEmpresa.Acao.values)

        self.assertTrue({
            'EQUIPAMENTOS', 'ESTOQUE', 'SICK', 'TRANSFERENCIAS',
            'EMPRESTIMOS', 'INSUMOS', 'CHECKLISTS', 'INVENTARIOS',
            'CHAMADOS', 'COMPRAS', 'CATALOGO', 'ORDENS_SERVICO',
            'AUDITORIAS', 'DOCUMENTACAO', 'INTEGRACOES', 'TORY',
            'USUARIOS',
        }.issubset(resources))
        self.assertEqual(actions, {
            'VISUALIZAR', 'CRIAR', 'EDITAR', 'MOVIMENTAR',
            'ATENDER', 'APROVAR', 'EXPORTAR', 'ADMINISTRAR',
        })


class CompanyRelationshipTenantScopeTests(TestCase):
    def setUp(self):
        self.company_a = Empresa.objects.create(nome='Scope Persistido A')
        self.company_b = Empresa.objects.create(nome='Scope Persistido B')
        self.user_admin_a = self._user(
            'relationship.admin.a', Perfil.Role.ADMIN, self.company_a
        )
        self.user_admin_b = self._user(
            'relationship.admin.b', Perfil.Role.ADMIN, self.company_b
        )

    @staticmethod
    def _user(username, role, company):
        user = User.objects.create_user(username=username, password='senha-de-teste')
        profile = user.perfil
        profile.role = role
        profile.empresa = company
        profile.save()
        return user

    def _relationship_with_capability(
        self,
        *,
        relationship_active=True,
        capability_active=True,
        resource=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
        action=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
    ):
        relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a,
            empresa_destino=self.company_b,
            ativo=relationship_active,
        )
        capability = CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=relationship,
            recurso=resource,
            acao=action,
            ativo=capability_active,
        )
        self.user_admin_a.perfil.empresas_acesso_adicional.add(
            relationship.empresa_destino
        )
        return relationship, capability

    def test_active_capability_adds_destination_to_admin_scope(self):
        self._relationship_with_capability()

        scope = TenantScope.for_user(self.user_admin_a)

        self.assertEqual(
            set(scope.visible_companies().values_list('pk', flat=True)),
            {self.company_a.pk, self.company_b.pk},
        )
        self.assertTrue(scope.can_view_company(self.company_b))
        self.assertTrue(scope.has_related_capability(
            self.company_b,
            CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
        ))

    def test_relationship_does_not_grant_inverse_access(self):
        self._relationship_with_capability()

        reverse_scope = TenantScope.for_user(self.user_admin_b)

        self.assertEqual(
            list(reverse_scope.visible_companies()),
            [self.company_b],
        )
        self.assertFalse(reverse_scope.can_view_company(self.company_a))

    def test_inactive_relationship_or_capability_grants_nothing(self):
        self._relationship_with_capability(relationship_active=False)
        inactive_cap_relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a,
            empresa_destino=Empresa.objects.create(nome='Scope Persistido C'),
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=inactive_cap_relationship,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.ESTOQUE,
            acao=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
            ativo=False,
        )
        self.user_admin_a.perfil.empresas_acesso_adicional.add(
            inactive_cap_relationship.empresa_destino
        )

        scope = TenantScope.for_user(self.user_admin_a)

        self.assertEqual(list(scope.visible_companies()), [self.company_a])

    def test_relationship_without_capabilities_grants_nothing(self):
        RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a,
            empresa_destino=self.company_b,
        )
        self.user_admin_a.perfil.empresas_acesso_adicional.add(self.company_b)

        scope = TenantScope.for_user(self.user_admin_a)

        self.assertFalse(scope.can_view_company(self.company_b))

    def test_gestor_does_not_inherit_company_relationship(self):
        self._relationship_with_capability()
        gestor = self._user(
            'relationship.gestor.a', Perfil.Role.GESTOR, self.company_a
        )

        scope = TenantScope.for_user(gestor)

        self.assertEqual(list(scope.visible_companies()), [self.company_a])
        self.assertFalse(scope.can_view_company(self.company_b))

    def test_operational_admin_capability_allows_related_management(self):
        self._relationship_with_capability(
            resource=CapacidadeRelacionamentoEmpresa.Recurso.OPERACAO,
            action=CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR,
        )

        scope = TenantScope.for_user(self.user_admin_a)

        self.assertTrue(scope.can_manage_company(self.company_a))
        self.assertTrue(scope.can_manage_company(self.company_b))

    def test_resource_admin_capability_is_not_tenant_wide_management(self):
        self._relationship_with_capability(
            resource=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            action=CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR,
        )

        scope = TenantScope.for_user(self.user_admin_a)

        self.assertTrue(scope.has_related_capability(
            self.company_b, 'CHAMADOS', 'ADMINISTRAR'
        ))
        self.assertFalse(scope.can_manage_company(self.company_b))


class CompanyRelationshipAdminTests(TestCase):
    def setUp(self):
        self.model_admin = admin.site._registry[RelacionamentoEmpresa]
        self.superuser = User.objects.create_superuser(
            username='relationship.platform.admin',
            email='platform@example.test',
            password='senha-de-teste',
        )
        self.tenant_admin = User.objects.create_user(
            username='relationship.tenant.admin',
            password='senha-de-teste',
            is_staff=True,
        )
        self.tenant_admin.perfil.role = Perfil.Role.ADMIN
        self.tenant_admin.perfil.save()

    def test_only_superuser_can_access_relationship_admin(self):
        super_request = SimpleNamespace(user=self.superuser)
        tenant_request = SimpleNamespace(user=self.tenant_admin)

        self.assertTrue(self.model_admin.has_module_permission(super_request))
        self.assertTrue(self.model_admin.has_view_permission(super_request))
        self.assertTrue(self.model_admin.has_add_permission(super_request))
        self.assertTrue(self.model_admin.has_change_permission(super_request))
        self.assertTrue(self.model_admin.has_delete_permission(super_request))

        self.assertFalse(self.model_admin.has_module_permission(tenant_request))
        self.assertFalse(self.model_admin.has_view_permission(tenant_request))
        self.assertFalse(self.model_admin.has_add_permission(tenant_request))
        self.assertFalse(self.model_admin.has_change_permission(tenant_request))
        self.assertFalse(self.model_admin.has_delete_permission(tenant_request))
