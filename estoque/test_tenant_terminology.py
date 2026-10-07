from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import translation

from estoque.models import Empresa, Modulo, ModuloEmpresa, Perfil, SecaoDocumentacaoEmpresa, TermoEmpresa
from estoque.services.documentation_section_service import DocumentationSectionService
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

        TermoEmpresa.objects.create(
            empresa=cls.company_b,
            chave=TermoEmpresa.Chave.EQUIPAMENTO,
            valor_singular='Ativo',
            valor_plural='Ativos',
        )
        for code, name in {
            Modulo.Codigo.EQUIPAMENTOS: 'Ativos',
            Modulo.Codigo.SICK: 'Oficina',
        }.items():
            ModuloEmpresa.objects.filter(
                empresa=cls.company_b,
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
            'Ativos',
        )
        self.assertEqual(response_b.context['tenant_module_labels']['sick'], 'Oficina')
        self.assertContains(response_b, 'Oficina')
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

    def test_navbar_dashboard_e_documentacao_traduzem_terminologia_configurada(self):
        self.admin_b.perfil.idioma = Perfil.Idioma.ES
        self.admin_b.perfil.save(update_fields=('idioma',))
        for codigo, nome in {
            SecaoDocumentacaoEmpresa.Codigo.MANUAIS: 'Manuais de equipamentos',
            SecaoDocumentacaoEmpresa.Codigo.DRIVERS: 'Drivers',
            SecaoDocumentacaoEmpresa.Codigo.CHECKLISTS: 'Checklist de clientes',
        }.items():
            SecaoDocumentacaoEmpresa.objects.update_or_create(
                empresa=self.company_b,
                codigo=codigo,
                defaults={'habilitado': True, 'nome_exibicao': nome},
            )

        self.client.force_login(self.admin_b)
        response = self.client.get(reverse('estoque:index'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['tenant_dashboard_label'], 'Activos')
        self.assertEqual(
            response.context['tenant_module_labels'][Modulo.Codigo.CADASTROS],
            'Registros',
        )
        self.assertContains(response, 'Panel de Activos')
        self.assertContains(response, 'Vista general: Activos')
        self.assertContains(response, 'Transferencias')
        self.assertContains(response, 'Registros')
        self.assertContains(response, 'Documentación')
        self.assertNotContains(response, 'Dashboard de Ativos')

        with translation.override('es'):
            sections = DocumentationSectionService.configuration(
                self.admin_b,
                tenant=self.company_b,
            )
        self.assertEqual(sections['manuais']['label'], 'Manuales de equipos')
        self.assertEqual(sections['drivers']['label'], 'Controladores')
        self.assertEqual(
            sections['checklists']['label'],
            'Lista de verificación de clientes',
        )
