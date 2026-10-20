from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from estoque.models import Base, Empresa
from insumos.forms import CadastroInsumoForm


class CadastroGestorAdminR3GTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa R3G')
        self.outra_empresa = Empresa.objects.create(nome='Outra R3G')
        self.base = Base.objects.create(nome='Base permitida R3G', empresa=self.empresa)
        self.outra_base = Base.objects.create(nome='Base proibida R3G', empresa=self.outra_empresa)

    def _user(self, username, role):
        user = User.objects.create_user(username=username, password='senha')
        user.perfil.role = role
        user.perfil.empresa = self.empresa
        user.perfil.save()
        user.perfil.regionais.add(self.base)
        return user

    def test_gestor_e_admin_acessam_cadastros(self):
        for role in ('gestor', 'admin'):
            with self.subTest(role=role):
                user = self._user(f'{role}-r3g', role)
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse('estoque:cadastrar_equipamento')).status_code, 200)
                self.assertEqual(self.client.get(reverse('insumos:cadastrar_insumos')).status_code, 200)
                form = CadastroInsumoForm(user=user)
                self.assertTrue(form.fields['base'].queryset.filter(pk=self.base.pk).exists())
                self.assertFalse(form.fields['base'].queryset.filter(pk=self.outra_base.pk).exists())
                self.client.logout()

    def test_operador_nao_acessa_cadastros(self):
        operador = self._user('operador-r3g', 'operador')
        self.client.force_login(operador)
        self.assertEqual(self.client.get(reverse('estoque:cadastrar_equipamento')).status_code, 403)
        self.assertEqual(self.client.get(reverse('insumos:cadastrar_insumos')).status_code, 403)
