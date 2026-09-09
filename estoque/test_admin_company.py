from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa, Perfil


class AdminCompanyModelTests(TestCase):
    def setUp(self):
        self.empresa_a = Empresa.objects.create(nome='Empresa Admin A')
        self.empresa_b = Empresa.objects.create(nome='Empresa Admin B')
        self.base_a = Base.objects.create(
            nome='Base Admin A',
            empresa=self.empresa_a,
        )

    def test_admin_preserva_empresa_e_deixa_de_ser_limitado_por_bases(self):
        user = User.objects.create_user('admin.com.empresa')
        perfil = user.perfil
        perfil.role = Perfil.Role.GESTOR
        perfil.empresa = self.empresa_a
        perfil.save()
        perfil.regionais.add(self.base_a)

        perfil.role = Perfil.Role.ADMIN
        perfil.empresa = self.empresa_b
        perfil.save()
        perfil.refresh_from_db()

        self.assertEqual(perfil.empresa, self.empresa_b)
        self.assertFalse(perfil.regionais.exists())

    def test_admin_legado_sem_empresa_continua_valido(self):
        user = User.objects.create_user('admin.legado')
        perfil = user.perfil
        perfil.role = Perfil.Role.ADMIN
        perfil.empresa = None

        perfil.save()
        perfil.refresh_from_db()

        self.assertIsNone(perfil.empresa)
        self.assertTrue(perfil.is_admin)

    def test_superuser_permanece_conceitualmente_separado_do_role_admin(self):
        user = User.objects.create_superuser(
            username='superuser.plataforma',
            email='superuser@example.test',
            password='SenhaDeTeste123!',
        )

        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertEqual(user.perfil.role, Perfil.Role.OPERADOR)
        self.assertIsNone(user.perfil.empresa)


class AdminCompanyUserManagementTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Cadastro Admin')
        self.base = Base.objects.create(
            nome='Base Cadastro Admin',
            empresa=self.empresa,
        )
        self.admin_criador = User.objects.create_user(
            'admin.criador',
            password='SenhaDeTeste123!',
        )
        self.admin_criador.perfil.role = Perfil.Role.ADMIN
        self.admin_criador.perfil.empresa = self.empresa
        self.admin_criador.perfil.save()
        self.client.force_login(self.admin_criador)

    def _dados_admin(self, **extras):
        dados = {
            'username': 'admin.novo.tenant',
            'password': 'SenhaDeTeste123!',
            'first_name': 'Admin',
            'last_name': 'Tenant',
            'perfil_acesso': 'admin',
            'empresa': str(self.empresa.pk),
            'is_active': 'on',
        }
        dados.update(extras)
        return dados

    def test_cadastro_de_admin_exige_empresa_mas_nao_exige_base(self):
        resposta = self.client.post(
            reverse('estoque:cadastrar_usuario'),
            self._dados_admin(),
        )

        self.assertRedirects(resposta, reverse('estoque:cadastrar_usuario'))
        user = User.objects.get(username='admin.novo.tenant')
        self.assertEqual(user.perfil.role, Perfil.Role.ADMIN)
        self.assertEqual(user.perfil.empresa, self.empresa)
        self.assertFalse(user.perfil.regionais.exists())
        self.assertFalse(user.is_superuser)

    def test_cadastro_de_admin_sem_empresa_e_rejeitado(self):
        resposta = self.client.post(
            reverse('estoque:cadastrar_usuario'),
            self._dados_admin(
                username='admin.sem.empresa',
                empresa='',
            ),
        )

        self.assertRedirects(resposta, reverse('estoque:cadastrar_usuario'))
        self.assertFalse(User.objects.filter(username='admin.sem.empresa').exists())

    def test_tela_classifica_admin_como_perfil_de_empresa_sem_bases(self):
        resposta = self.client.get(reverse('estoque:cadastrar_usuario'))

        self.assertEqual(resposta.status_code, 200)
        admin_config = next(
            perfil
            for perfil in resposta.context['perfis_acesso']
            if perfil['value'] == 'admin'
        )
        self.assertFalse(admin_config['global'])
        self.assertFalse(admin_config['exige_bases'])
        self.assertContains(resposta, 'data-exige-bases="0"')
        self.assertContains(resposta, 'function perfilExigeBases()')

    def test_admin_de_tenant_nao_acessa_painel_superuser(self):
        resposta_tela = self.client.get(reverse('estoque:cadastrar_usuario'))
        self.assertNotContains(resposta_tela, reverse('admin:index'))

        resposta_admin = self.client.get(reverse('admin:index'))
        self.assertEqual(resposta_admin.status_code, 302)

    def test_superuser_acessa_painel_e_visualiza_link_exclusivo(self):
        superuser = User.objects.create_superuser(
            username='admin.plataforma',
            email='admin.plataforma@example.test',
            password='SenhaDeTeste123!',
        )
        superuser.perfil.role = Perfil.Role.ADMIN
        superuser.perfil.empresa = self.empresa
        superuser.perfil.save()
        self.client.force_login(superuser)

        resposta_tela = self.client.get(reverse('estoque:cadastrar_usuario'))
        self.assertContains(resposta_tela, reverse('admin:index'))
        self.assertContains(resposta_tela, 'Painel Superuser')
        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 200)
