from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, Equipamento, Perfil, Produto


class IndexFinalidadeFilterTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Inventory Teste')
        self.regional = Base.objects.create(nome='Regional Teste', empresa=self.empresa)
        self.produto = Produto.objects.create(
            codigo='PROD-INDEX-1',
            descricao='Coletor de teste',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Coletores',
        )
        self.usuario = User.objects.create_user(username='admin_index', password='senha')
        perfil = self.usuario.perfil
        perfil.role = Perfil.Role.ADMIN
        perfil.empresa = self.empresa
        perfil.save(update_fields=['role', 'empresa'])
        self.client.force_login(self.usuario)

        for finalidade in Equipamento.Finalidade.values:
            Equipamento.objects.create(
                produto=self.produto,
                numero_serie=f'SERIE-{finalidade}',
                patrimonio=f'PAT-{finalidade}',
                regional=self.regional,
                status='ATIVO',
                finalidade=finalidade,
                codigo=f'EQP-{finalidade}',
            )

    def test_filtra_equipamentos_operacionais(self):
        response = self.client.get(
            reverse('estoque:index'),
            {'finalidade': Equipamento.Finalidade.OPERACIONAL},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['filtro_finalidade'], 'OPERACIONAL')
        self.assertEqual(response.context['kpis_totais']['total'], 1)
        self.assertEqual(response.context['kpis_totais']['ativos'], 1)
        self.assertEqual(response.context['kpis_totais']['administrativos'], 0)
        self.assertContains(response, 'value="OPERACIONAL" selected')

    def test_filtra_equipamentos_administrativos(self):
        response = self.client.get(
            reverse('estoque:index'),
            {'finalidade': Equipamento.Finalidade.ADMINISTRATIVO},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['filtro_finalidade'], 'ADMINISTRATIVO')
        self.assertEqual(response.context['kpis_totais']['total'], 1)
        self.assertEqual(response.context['kpis_totais']['ativos'], 0)
        self.assertEqual(response.context['kpis_totais']['administrativos'], 1)
        self.assertContains(response, 'value="ADMINISTRATIVO" selected')
