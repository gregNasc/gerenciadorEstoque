from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from estoque.models import Empresa, Modulo, ModuloEmpresa, Perfil, TermoEmpresa
from estoque.services.tenant_terminology_service import TenantTerminologyService


class TenantTerminologyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company_a = Empresa.objects.create(nome='Terminologia Alpha')
        cls.company_b = Empresa.objects.create(nome='Terminologia Beta')
        cls.admin_a = cls._admin('terminologia.admin.a', cls.company_a)
        cls.admin_b = cls._admin('terminologia.admin.b', cls.company_b)

        custom_terms = {
            TermoEmpresa.Chave.EQUIPAMENTO: ('Máquina', 'Máquinas'),
            TermoEmpresa.Chave.BASE: ('Unidade', 'Unidades'),
            TermoEmpresa.Chave.REGIONAL: ('Setor', 'Setores'),
            TermoEmpresa.Chave.MANUTENCAO: ('Reparo', 'Reparos'),
            TermoEmpresa.Chave.USUARIO: ('Colaborador', 'Colaboradores'),
        }
        for key, values in custom_terms.items():
            TermoEmpresa.objects.create(
                empresa=cls.company_a,
                chave=key,
                valor_singular=values[0],
                valor_plural=values[1],
            )

        custom_modules = {
            Modulo.Codigo.ESTOQUE: 'Ativos',
            Modulo.Codigo.EQUIPAMENTOS: 'Máquinas',
            Modulo.Codigo.SICK: 'Manutenção',
            Modulo.Codigo.USUARIOS: 'Equipe',
            Modulo.Codigo.CADASTROS: 'Registros',
        }
        for code, name in custom_modules.items():
            ModuloEmpresa.objects.filter(
                empresa=cls.company_a,
                modulo__codigo=code,
            ).update(nome_exibicao=name)

    @staticmethod
    def _admin(username, company):
        user = User.objects.create_user(username, password='Teste123!')
        user.perfil.role = Perfil.Role.ADMIN
        user.perfil.empresa = company
        user.perfil.save(update_fields=('role', 'empresa'))
        return user

    def test_service_resolves_custom_terms_and_module_names(self):
        labels = TenantTerminologyService.labels(self.company_a)
        modules = TenantTerminologyService.module_labels(self.company_a)

        self.assertEqual(labels['equipamento']['singular'], 'Máquina')
        self.assertEqual(labels['equipamento']['plural'], 'Máquinas')
        self.assertEqual(labels['base']['plural'], 'Unidades')
        self.assertEqual(labels['regional']['singular'], 'Setor')
        self.assertEqual(modules['sick'], 'Manutenção')
        self.assertEqual(modules['usuarios'], 'Equipe')

    def test_request_cache_avoids_repeating_tenant_queries(self):
        request = RequestFactory().get('/')
        request.tenant = self.company_a

        with self.assertNumQueries(2):
            first = TenantTerminologyService.context_for_request(request)
        with self.assertNumQueries(0):
            second = TenantTerminologyService.context_for_request(request)

        self.assertIs(first, second)

    def test_custom_terminology_is_rendered_only_for_its_tenant(self):
        self.client.force_login(self.admin_a)
        response_a = self.client.get(reverse('estoque:index'))

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(
            response_a.context['tenant_labels']['equipamento']['plural'],
            'Máquinas',
        )
        self.assertContains(response_a, 'Dashboard de Ativos')
        self.assertContains(response_a, 'Manutenção')
        self.assertContains(response_a, 'Setor')

        self.client.force_login(self.admin_b)
        response_b = self.client.get(reverse('estoque:index'))

        self.assertEqual(response_b.status_code, 200)
        self.assertEqual(
            response_b.context['tenant_labels']['equipamento']['plural'],
            'Equipamentos',
        )
        self.assertEqual(response_b.context['tenant_module_labels']['sick'], 'SICK')
        self.assertNotContains(response_b, 'Unidades')
        self.assertNotContains(response_b, 'Máquinas')

    def test_missing_or_blank_values_fall_back_to_platform_defaults(self):
        TermoEmpresa.objects.create(
            empresa=self.company_b,
            chave=TermoEmpresa.Chave.DOCUMENTACAO,
            valor_singular=' ',
            valor_plural='',
        )

        labels = TenantTerminologyService.labels(self.company_b)

        self.assertEqual(labels['documentacao']['singular'], 'Documentação')
        self.assertEqual(labels['documentacao']['plural'], 'Documentações')
