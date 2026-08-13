from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from chamados.policies import GruposChamados
from estoque.models import Base, Empresa, Perfil
from estoque.policies.compras import GruposCorporativos


class CadastroCapacidadesUsuarioTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Perfis')
        self.base = Base.objects.create(empresa=self.empresa, nome='Base Perfis')
        self.admin = User.objects.create_user('admin.perfis', password='SenhaForte123!')
        self.admin.perfil.role = Perfil.Role.ADMIN
        self.admin.perfil.save(update_fields=['role'])
        self.client.force_login(self.admin)

    def _dados(self, **extras):
        dados = {
            'username': 'operador.capacidade',
            'password': 'SenhaForte123!',
            'first_name': 'Operador',
            'last_name': 'Capacidade',
            'perfil_acesso': 'operador',
            'empresa': str(self.empresa.pk),
            'regionais': [str(self.base.pk)],
            'is_active': 'on',
        }
        dados.update(extras)
        return dados

    def test_cadastro_define_suporte_ou_sick_e_remove_capacidade_anterior(self):
        resposta = self.client.post(
            reverse('estoque:cadastrar_usuario'),
            self._dados(usuario_suporte='on'),
        )
        self.assertEqual(resposta.status_code, 302)
        usuario = User.objects.get(username='operador.capacidade')
        self.assertTrue(usuario.groups.filter(name=GruposChamados.SUPORTE).exists())
        self.assertTrue(usuario.groups.filter(name=GruposChamados.DASHBOARD).exists())
        self.assertFalse(usuario.groups.filter(name=GruposCorporativos.SICK_GERENCIAR).exists())

        resposta = self.client.post(
            reverse('estoque:cadastrar_usuario'),
            self._dados(
                usuario_id=str(usuario.pk),
                password='',
                usuario_sick='on',
            ),
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(usuario.groups.filter(name=GruposChamados.SUPORTE).exists())
        self.assertFalse(usuario.groups.filter(name=GruposChamados.DASHBOARD).exists())
        self.assertTrue(usuario.groups.filter(name=GruposCorporativos.SICK_GERENCIAR).exists())
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse('estoque:sick')).status_code, 200)


class EscopoOperadorTests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(nome='Empresa Operador')
        base = Base.objects.create(empresa=empresa, nome='Base Operador')
        self.operador = User.objects.create_user('operador.restrito', password='SenhaForte123!')
        self.operador.perfil.empresa = empresa
        self.operador.perfil.role = Perfil.Role.OPERADOR
        self.operador.perfil.save()
        self.operador.perfil.regionais.add(base)
        self.client.force_login(self.operador)

    def test_operador_acessa_somente_manuais_chamados_e_comunicados(self):
        self.assertEqual(self.client.get(reverse('estoque:index')).status_code, 302)
        self.assertEqual(self.client.get(reverse('estoque:manuais')).status_code, 200)
        self.assertEqual(self.client.get(reverse('chamados:lista')).status_code, 200)
        self.assertEqual(self.client.get(reverse('estoque:caixa_comunicados')).status_code, 200)
        self.assertEqual(self.client.get(reverse('estoque:estoque')).status_code, 403)
        self.assertEqual(self.client.get(reverse('estoque:sick')).status_code, 403)
        self.assertEqual(self.client.get(reverse('compras:valores_equipamentos')).status_code, 403)

    def test_dashboard_exige_usuario_de_suporte(self):
        self.assertEqual(self.client.get(reverse('chamados:dashboard')).status_code, 403)
        self.operador.groups.add(Group.objects.get(name=GruposChamados.SUPORTE))
        self.assertEqual(self.client.get(reverse('chamados:dashboard')).status_code, 200)

    def test_tecnico_de_manutencao_sick_acessa_tela_sick(self):
        grupo, _ = Group.objects.get_or_create(name=GruposCorporativos.SICK_MANUTENCAO)
        self.operador.groups.add(grupo)
        self.assertEqual(self.client.get(reverse('estoque:sick')).status_code, 200)
