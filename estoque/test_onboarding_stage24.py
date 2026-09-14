from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Modulo,
    ModuloEmpresa,
    Perfil,
    RelacionamentoEmpresa,
)


class TenantOnboardingStage24Tests(TestCase):
    def setUp(self):
        self.existing_company = Empresa.objects.create(
            nome='Empresa Existente 24',
            slug='empresa-existente-24',
        )
        self.superuser = User.objects.create_superuser(
            username='root.onboarding.24',
            email='root-onboarding-24@example.test',
            password='Senha-Root-Somente-Teste-24!',
        )
        self.root_password_hash = self.superuser.password
        self.client.force_login(self.superuser)

    @staticmethod
    def step_url(step, company=None):
        url = reverse('estoque:onboarding_empresa_etapa', args=(step,))
        return f'{url}?empresa={company.pk}' if company else url

    def test_complete_flow_keeps_tenant_inactive_until_final_validation(self):
        response = self.client.get(
            f'{reverse("estoque:onboarding_empresa")}?novo=1'
        )
        self.assertRedirects(response, self.step_url('dados'))

        response = self.client.post(self.step_url('dados'), {
            'nome': 'Empresa Nova Etapa 24',
            'slug': 'empresa-nova-etapa-24',
        })
        company = Empresa.objects.get(slug='empresa-nova-etapa-24')
        self.assertFalse(company.ativa)
        self.assertRedirects(response, self.step_url('modulos', company))

        selected_modules = [
            Modulo.Codigo.ESTOQUE,
            Modulo.Codigo.EQUIPAMENTOS,
            Modulo.Codigo.CHAMADOS,
        ]
        response = self.client.post(self.step_url('modulos', company), {
            'modulos': selected_modules,
        })
        self.assertRedirects(response, self.step_url('admin', company))
        self.assertEqual(
            set(ModuloEmpresa.objects.filter(
                empresa=company,
                habilitado=True,
            ).values_list('modulo__codigo', flat=True)),
            set(selected_modules),
        )

        response = self.client.post(self.step_url('admin', company), {
            'username': 'primeiro.admin.etapa24',
            'first_name': 'Primeiro',
            'last_name': 'Admin',
            'email': 'primeiro-admin-24@example.test',
            'password': 'Senha-Inicial-Segura-24!x',
            'password_confirmation': 'Senha-Inicial-Segura-24!x',
        })
        self.assertRedirects(response, self.step_url('bases', company))
        first_admin = User.objects.get(username='primeiro.admin.etapa24')
        self.assertFalse(first_admin.is_superuser)
        self.assertFalse(first_admin.is_staff)
        self.assertTrue(first_admin.is_active)
        self.assertTrue(first_admin.check_password('Senha-Inicial-Segura-24!x'))
        self.assertEqual(first_admin.perfil.empresa, company)
        self.assertEqual(first_admin.perfil.role, Perfil.Role.ADMIN)

        response = self.client.post(self.step_url('bases', company), {
            'bases': 'Base Norte 24\nBase Sul 24\nBase Norte 24',
        })
        self.assertRedirects(response, self.step_url('relacionamentos', company))
        self.assertEqual(company.bases.count(), 2)

        response = self.client.post(self.step_url('relacionamentos', company), {
            'relacionamentos': [str(self.existing_company.pk)],
            f'suporte_{self.existing_company.pk}': '1',
        })
        self.assertRedirects(response, self.step_url('revisar', company))
        relationship = RelacionamentoEmpresa.objects.get(
            empresa_origem=company,
            empresa_destino=self.existing_company,
        )
        self.assertTrue(relationship.ativo)
        self.assertTrue(relationship.compartilha_suporte_chamados)
        self.assertTrue(
            CapacidadeRelacionamentoEmpresa.objects.filter(
                relacionamento=relationship,
                recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
                acao=CapacidadeRelacionamentoEmpresa.Acao.ATENDER,
                ativo=True,
            ).exists()
        )

        company.refresh_from_db()
        self.assertFalse(company.ativa)
        response = self.client.post(self.step_url('revisar', company))
        self.assertRedirects(response, reverse('estoque:painel_superuser'))
        company.refresh_from_db()
        self.assertTrue(company.ativa)

        self.superuser.refresh_from_db()
        self.assertEqual(self.superuser.password, self.root_password_hash)

    def test_cannot_activate_without_explicit_modules_or_first_admin(self):
        company = Empresa.objects.create(
            nome='Tenant Incompleto 24',
            slug='tenant-incompleto-24',
            ativa=False,
        )

        response = self.client.post(self.step_url('revisar', company))

        self.assertRedirects(response, self.step_url('modulos', company))
        company.refresh_from_db()
        self.assertFalse(company.ativa)

        for config in company.modulos_configurados.all():
            config.configurado_por = self.superuser
            config.save(update_fields=['configurado_por'])
        response = self.client.post(self.step_url('revisar', company))
        self.assertRedirects(response, self.step_url('admin', company))
        company.refresh_from_db()
        self.assertFalse(company.ativa)

    def test_admin_password_errors_do_not_create_partial_user(self):
        company = Empresa.objects.create(
            nome='Tenant Senha Inválida 24',
            slug='tenant-senha-invalida-24',
            ativa=False,
        )

        response = self.client.post(self.step_url('admin', company), {
            'username': 'admin.parcial.24',
            'password': '123',
            'password_confirmation': 'diferente',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='admin.parcial.24').exists())
        self.assertFalse(response.context['admins_onboarding'])

    def test_cancel_keeps_partial_tenant_inactive(self):
        company = Empresa.objects.create(
            nome='Tenant Pausado 24',
            slug='tenant-pausado-24',
            ativa=False,
        )

        response = self.client.post(self.step_url('bases', company), {
            'acao': 'cancelar',
        })

        self.assertRedirects(response, reverse('estoque:painel_superuser'))
        company.refresh_from_db()
        self.assertFalse(company.ativa)
        self.assertTrue(Empresa.objects.filter(pk=company.pk).exists())

    def test_tenant_admin_cannot_open_or_post_onboarding(self):
        admin = User.objects.create_user(
            username='admin.sem.onboarding.24',
            password='Senha-Somente-Teste-24!',
        )
        admin.perfil.empresa = self.existing_company
        admin.perfil.role = Perfil.Role.ADMIN
        admin.perfil.save(update_fields=['empresa', 'role'])
        self.client.force_login(admin)

        self.assertEqual(
            self.client.get(reverse('estoque:onboarding_empresa')).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(self.step_url('dados'), {'nome': 'Intrusa 24'}).status_code,
            403,
        )
        self.assertFalse(Empresa.objects.filter(nome__iexact='Intrusa 24').exists())


class TenantMembershipHardeningStage24Tests(TestCase):
    def setUp(self):
        self.active_company = Empresa.objects.create(
            nome='Empresa Ativa Hardening 24',
            slug='empresa-ativa-hardening-24',
        )
        self.inactive_company = Empresa.objects.create(
            nome='Empresa Inativa Hardening 24',
            slug='empresa-inativa-hardening-24',
            ativa=False,
        )

    def test_active_non_superuser_profile_requires_company_on_validation(self):
        user = User.objects.create_user('orfao.validacao.24')

        with self.assertRaises(ValidationError):
            user.perfil.full_clean()

        user.is_active = False
        user.save(update_fields=['is_active'])
        user.perfil.full_clean()

    def test_middleware_blocks_missing_or_inactive_tenant_but_not_superuser(self):
        orphan = User.objects.create_user('orfao.middleware.24')
        self.client.force_login(orphan)
        self.assertEqual(self.client.get(reverse('estoque:caixa_comunicados')).status_code, 403)

        inactive = User.objects.create_user('inativo.middleware.24')
        inactive.perfil.empresa = self.inactive_company
        inactive.perfil.save(update_fields=['empresa'])
        self.client.force_login(inactive)
        self.assertEqual(self.client.get(reverse('estoque:caixa_comunicados')).status_code, 403)

        root = User.objects.create_superuser('root.middleware.24')
        self.client.force_login(root)
        self.assertEqual(self.client.get(reverse('estoque:painel_superuser')).status_code, 200)

    def test_cross_tenant_bases_are_rejected_on_profile_relations(self):
        other_company = Empresa.objects.create(
            nome='Outra Empresa Hardening 24',
            slug='outra-empresa-hardening-24',
        )
        own_base = Base.objects.create(nome='Base Própria 24', empresa=self.active_company)
        foreign_base = Base.objects.create(nome='Base Estrangeira 24', empresa=other_company)
        user = User.objects.create_user('bases.hardening.24')
        user.perfil.empresa = self.active_company
        user.perfil.save(update_fields=['empresa'])

        user.perfil.regionais.add(own_base)
        with self.assertRaises(ValidationError), transaction.atomic():
            user.perfil.regionais.add(foreign_base)
        with self.assertRaises(ValidationError), transaction.atomic():
            user.perfil.bases_checklist.add(foreign_base)

    def test_company_slug_is_generated_and_unique(self):
        first = Empresa.objects.create(nome='Tenant Sem Slug 24')
        second = Empresa.objects.create(nome='Tenant Sem Slug 24 - Outra')

        self.assertTrue(first.slug)
        self.assertTrue(second.slug)
        self.assertNotEqual(first.slug, second.slug)
