from django.contrib.auth.models import User
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


class SuperuserPanelStage23Tests(TestCase):
    def setUp(self):
        self.company_a = Empresa.objects.create(
            nome='Empresa Painel 23 A',
            slug='empresa-painel-23-a',
        )
        self.company_b = Empresa.objects.create(
            nome='Empresa Painel 23 B',
            slug='empresa-painel-23-b',
        )
        self.base = Base.objects.create(
            nome='Base Painel 23',
            empresa=self.company_a,
        )
        self.first_admin = User.objects.create_user(
            username='primeiro.admin.23',
            first_name='Primeiro',
            last_name='Admin',
            password='senha-somente-teste-23',
        )
        self.first_admin.perfil.role = Perfil.Role.ADMIN
        self.first_admin.perfil.empresa = self.company_a
        self.first_admin.perfil.save(update_fields=['role', 'empresa'])
        self.tenant_admin = User.objects.create_user(
            username='admin.tenant.23',
            password='senha-somente-teste-23',
        )
        self.tenant_admin.perfil.role = Perfil.Role.ADMIN
        self.tenant_admin.perfil.empresa = self.company_b
        self.tenant_admin.perfil.save(update_fields=['role', 'empresa'])
        self.superuser = User.objects.create_superuser(
            username='root.painel.23',
            email='root-painel-23@example.test',
            password='senha-somente-teste-23',
        )
        self.relationship = RelacionamentoEmpresa.objects.create(
            empresa_origem=self.company_a,
            empresa_destino=self.company_b,
            ativo=True,
            compartilha_suporte_chamados=True,
            criado_por=self.superuser,
        )
        CapacidadeRelacionamentoEmpresa.objects.create(
            relacionamento=self.relationship,
            recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            acao=CapacidadeRelacionamentoEmpresa.Acao.ATENDER,
            criado_por=self.superuser,
        )
        self.url = reverse('estoque:painel_superuser')

    def test_only_superuser_can_open_panel(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

        self.client.force_login(self.tenant_admin)
        self.assertEqual(self.client.get(self.url).status_code, 403)

        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_panel_exposes_every_stage_23_dimension(self):
        self.client.force_login(self.superuser)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        company = next(
            item for item in response.context['empresas']
            if item.pk == self.company_a.pk
        )
        self.assertTrue(company.ativa)
        self.assertEqual(company.primeiro_admin, self.first_admin)
        self.assertEqual(company.total_usuarios, 1)
        self.assertEqual(company.total_usuarios_ativos, 1)
        self.assertEqual(company.total_bases, 1)
        self.assertEqual(company.total_relacionamentos, 1)
        self.assertEqual(
            company.total_modulos_habilitados,
            Modulo.objects.filter(ativo=True).count(),
        )
        self.assertContains(response, self.company_a.nome)
        self.assertContains(response, '@primeiro.admin.23')
        self.assertContains(response, 'Relacionamentos entre empresas')
        self.assertContains(response, 'Compartilhado')
        self.assertContains(
            response,
            f'{reverse("estoque:index")}?inventory={self.company_a.pk}',
        )

    def test_superuser_can_configure_modules_and_audit_actor(self):
        self.client.force_login(self.superuser)
        enabled_codes = list(
            Modulo.objects.filter(ativo=True)
            .exclude(codigo=Modulo.Codigo.CHAMADOS)
            .values_list('codigo', flat=True)
        )

        response = self.client.post(self.url, {
            'acao': 'configurar_modulos',
            'empresa': self.company_a.pk,
            'modulos': enabled_codes,
        })

        self.assertRedirects(response, self.url)
        calls_config = ModuloEmpresa.objects.get(
            empresa=self.company_a,
            modulo__codigo=Modulo.Codigo.CHAMADOS,
        )
        self.assertFalse(calls_config.habilitado)
        self.assertEqual(calls_config.configurado_por, self.superuser)
        self.assertFalse(
            ModuloEmpresa.objects.filter(
                empresa=self.company_a,
                habilitado=False,
            ).exclude(pk=calls_config.pk).exists()
        )
        self.assertTrue(
            ModuloEmpresa.objects.filter(
                empresa=self.company_b,
                modulo__codigo=Modulo.Codigo.CHAMADOS,
                habilitado=True,
            ).exists()
        )

    def test_tenant_admin_cannot_change_module_configuration(self):
        config = ModuloEmpresa.objects.get(
            empresa=self.company_a,
            modulo__codigo=Modulo.Codigo.TORY,
        )
        self.client.force_login(self.tenant_admin)

        response = self.client.post(self.url, {
            'acao': 'configurar_modulos',
            'empresa': self.company_a.pk,
            'modulos': [],
        })

        self.assertEqual(response.status_code, 403)
        config.refresh_from_db()
        self.assertTrue(config.habilitado)

    def test_invalid_module_payload_is_rejected_without_partial_update(self):
        self.client.force_login(self.superuser)
        before = list(
            ModuloEmpresa.objects.filter(empresa=self.company_a)
            .order_by('modulo_id')
            .values_list('modulo_id', 'habilitado')
        )

        response = self.client.post(self.url, {
            'acao': 'configurar_modulos',
            'empresa': self.company_a.pk,
            'modulos': [Modulo.Codigo.ESTOQUE, 'modulo-inexistente'],
        })

        self.assertRedirects(response, self.url)
        after = list(
            ModuloEmpresa.objects.filter(empresa=self.company_a)
            .order_by('modulo_id')
            .values_list('modulo_id', 'habilitado')
        )
        self.assertEqual(after, before)

    def test_superuser_can_change_company_status(self):
        self.client.force_login(self.superuser)

        response = self.client.post(self.url, {
            'acao': 'alterar_status_empresa',
            'empresa': self.company_a.pk,
            'ativa': '0',
        })

        self.assertRedirects(response, self.url)
        self.company_a.refresh_from_db()
        self.assertFalse(self.company_a.ativa)

        response = self.client.post(self.url, {
            'acao': 'alterar_status_empresa',
            'empresa': self.company_a.pk,
            'ativa': '1',
        })
        self.assertRedirects(response, self.url)
        self.company_a.refresh_from_db()
        self.assertTrue(self.company_a.ativa)

    def test_legacy_new_company_action_enters_secure_onboarding(self):
        self.client.force_login(self.superuser)

        response = self.client.post(self.url, {
            'acao': 'criar_empresa',
            'nome': 'Empresa Nova Painel 23',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f'{reverse("estoque:onboarding_empresa")}?novo=1',
        )
        self.assertFalse(
            Empresa.objects.filter(nome__iexact='Empresa Nova Painel 23').exists()
        )
