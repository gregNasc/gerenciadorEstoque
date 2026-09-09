from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Perfil,
    RelacionamentoEmpresa,
)


class UserManagementTenantIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brasil = Empresa.objects.create(
            nome='Inventory Brasil isolamento usuarios',
            slug='inventory-brasil-isolamento-usuarios',
        )
        cls.latam = Empresa.objects.create(
            nome='Inventory LATAM isolamento usuarios',
            slug='inventory-latam-isolamento-usuarios',
        )
        cls.oxxo = Empresa.objects.create(
            nome='OXXO isolamento usuarios',
            slug='oxxo-isolamento-usuarios',
        )
        cls.antropic = Empresa.objects.create(
            nome='Antropic confidencial',
            slug='antropic-confidencial',
        )
        cls.base_brasil = Base.objects.create(
            empresa=cls.brasil, nome='Base Brasil usuarios'
        )
        cls.base_latam = Base.objects.create(
            empresa=cls.latam, nome='Base LATAM usuarios'
        )
        cls.base_oxxo = Base.objects.create(
            empresa=cls.oxxo, nome='Base OXXO usuarios'
        )
        cls.base_antropic = Base.objects.create(
            empresa=cls.antropic, nome='Base Antropic secreta'
        )
        for destination in (cls.latam, cls.oxxo):
            relationship = RelacionamentoEmpresa.objects.create(
                empresa_origem=cls.brasil,
                empresa_destino=destination,
            )
            CapacidadeRelacionamentoEmpresa.objects.create(
                relacionamento=relationship,
                recurso=CapacidadeRelacionamentoEmpresa.Recurso.OPERACAO,
                acao=CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR,
            )

        cls.edson = User.objects.create_user(
            'edson.nunes.isolamento', password='SenhaTeste123!'
        )
        cls.edson.perfil.role = Perfil.Role.ADMIN
        cls.edson.perfil.empresa = cls.brasil
        cls.edson.perfil.save()
        cls.edson.perfil.empresas_acesso_adicional.add(cls.latam, cls.oxxo)

        cls.user_antropic = User.objects.create_user(
            'usuario.antropic.confidencial', password='SenhaTeste123!'
        )
        cls.user_antropic.perfil.role = Perfil.Role.ADMIN
        cls.user_antropic.perfil.empresa = cls.antropic
        cls.user_antropic.perfil.save()
        cls.url = reverse('estoque:cadastrar_usuario')

    def setUp(self):
        self.client.force_login(self.edson)

    def test_inventory_admin_never_receives_unrelated_company_data(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.context['empresas']),
            {self.brasil, self.latam, self.oxxo},
        )
        self.assertNotIn(self.base_antropic, response.context['regionais'])
        self.assertNotIn(self.user_antropic, response.context['usuarios'])
        self.assertNotContains(response, 'Antropic confidencial')
        self.assertNotContains(response, 'Base Antropic secreta')
        self.assertNotContains(response, 'usuario.antropic.confidencial')

    def test_forged_external_company_cannot_be_used_to_create_user(self):
        response = self.client.post(self.url, {
            'username': 'usuario.forjado.antropic',
            'password': 'SenhaTeste123!',
            'first_name': 'Forjado',
            'perfil_acesso': 'admin',
            'empresa': str(self.antropic.pk),
            'is_active': 'on',
        })

        self.assertRedirects(response, self.url)
        self.assertFalse(
            User.objects.filter(username='usuario.forjado.antropic').exists()
        )

    def test_forged_external_user_id_cannot_be_changed(self):
        response = self.client.post(self.url, {
            'acao_usuario': 'inativar',
            'usuario_id': str(self.user_antropic.pk),
        })

        self.assertRedirects(response, self.url)
        self.user_antropic.refresh_from_db()
        self.assertTrue(self.user_antropic.is_active)

    def test_latam_and_oxxo_admins_only_receive_their_own_company(self):
        for company, username in (
            (self.latam, 'admin.latam.isolamento'),
            (self.oxxo, 'admin.oxxo.isolamento'),
        ):
            with self.subTest(company=company.nome):
                tenant_admin = User.objects.create_user(
                    username, password='SenhaTeste123!'
                )
                tenant_admin.perfil.role = Perfil.Role.ADMIN
                tenant_admin.perfil.empresa = company
                tenant_admin.perfil.save()
                self.client.force_login(tenant_admin)

                response = self.client.get(self.url)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(list(response.context['empresas']), [company])
                self.assertNotContains(response, 'Antropic confidencial')
                self.assertNotContains(response, self.brasil.nome)

    def test_only_superuser_can_see_every_company(self):
        platform_admin = User.objects.create_superuser(
            'platform.admin.isolamento', password='SenhaTeste123!'
        )
        platform_admin.perfil.role = Perfil.Role.ADMIN
        platform_admin.perfil.save(update_fields=['role'])
        self.client.force_login(platform_admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.antropic, response.context['empresas'])
        self.assertIn(self.user_antropic, response.context['usuarios'])

        panel = self.client.get(reverse('estoque:painel_superuser'))
        self.assertEqual(panel.status_code, 200)
        self.assertContains(panel, 'Central de administração')
        self.assertIn(self.antropic, panel.context['empresas'])
        self.assertContains(panel, 'companySearch')
