from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from chamados.policies import GruposChamados
from estoque.models import AuditoriaPermissaoUsuario, Base, Empresa, Perfil
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
        self.assertFalse(usuario.groups.filter(name=GruposChamados.DASHBOARD).exists())
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

    def test_permissao_delegada_e_auditada_e_status_e_acao_separada(self):
        codigo = 'chamados.atender_chamado'
        resposta = self.client.post(
            reverse('estoque:cadastrar_usuario'),
            self._dados(permissoes=[codigo]),
        )
        self.assertEqual(resposta.status_code, 302)
        usuario = User.objects.get(username='operador.capacidade')
        self.assertTrue(usuario.has_perm(codigo))
        auditoria = AuditoriaPermissaoUsuario.objects.get(usuario=usuario, permissao=codigo)
        self.assertFalse(auditoria.valor_anterior)
        self.assertTrue(auditoria.valor_novo)
        self.assertEqual(auditoria.alterado_por, self.admin)

        self.client.post(
            reverse('estoque:cadastrar_usuario'),
            {'acao_usuario': 'inativar', 'usuario_id': usuario.pk},
        )
        usuario.refresh_from_db()
        self.assertFalse(usuario.is_active)
        self.assertTrue(User.objects.filter(pk=usuario.pk).exists())
        self.client.post(
            reverse('estoque:cadastrar_usuario'),
            {'acao_usuario': 'reativar', 'usuario_id': usuario.pk},
        )
        usuario.refresh_from_db()
        self.assertTrue(usuario.is_active)

    def test_qualquer_admin_visualiza_menu_e_pode_criar_usuario(self):
        outro_admin = User.objects.create_user(
            'outro.admin',
            password='SenhaForte123!',
            is_staff=False,
        )
        outro_admin.perfil.role = Perfil.Role.ADMIN
        outro_admin.perfil.save(update_fields=['role'])
        self.assertNotEqual(outro_admin.pk, 1)
        self.assertFalse(outro_admin.is_superuser)
        self.client.force_login(outro_admin)

        url = reverse('estoque:cadastrar_usuario')
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, f'href="{url}"')

        resposta = self.client.post(
            url,
            self._dados(username='criado.por.outro.admin'),
        )
        self.assertRedirects(resposta, url)
        self.assertTrue(
            User.objects.filter(username='criado.por.outro.admin').exists()
        )


class EscopoOperadorTests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(nome='Empresa Operador')
        base = Base.objects.create(empresa=empresa, nome='Base Operador')
        self.base = base
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
        suporte, _ = Group.objects.get_or_create(name=GruposChamados.SUPORTE)
        self.operador.groups.add(suporte)
        self.assertEqual(self.client.get(reverse('chamados:dashboard')).status_code, 403)
        self.operador.user_permissions.add(Permission.objects.get(
            codename='visualizar_dashboard_chamado', content_type__app_label='chamados'
        ))
        self.assertEqual(self.client.get(reverse('chamados:dashboard')).status_code, 200)

    def test_tecnico_de_manutencao_sick_acessa_tela_sick(self):
        grupo, _ = Group.objects.get_or_create(name=GruposCorporativos.SICK_MANUTENCAO)
        self.operador.groups.add(grupo)
        self.assertEqual(self.client.get(reverse('estoque:sick')).status_code, 200)

    def test_permissoes_de_checklist_exibem_menu_para_operador(self):
        self.operador.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='insumos',
            codename__in=['preencher_checklists', 'visualizar_checklists'],
        ))
        self.operador.perfil.bases_checklist.add(self.base)

        response = self.client.get(reverse('estoque:checklist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="checklistDropdown"')
        self.assertContains(response, reverse('estoque:checklist'))
        self.assertContains(response, reverse('insumos:lista_checklists'))
