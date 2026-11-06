from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from estoque.models import Empresa, Perfil


class UsuarioLatamIdiomaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.latam = Empresa.objects.create(
            nome='Inventory LATAM',
            slug='inventory-latam',
        )
        cls.brasil = Empresa.objects.create(
            nome='Inventory Brasil',
            slug='inventory-brasil',
        )
        cls.superuser = User.objects.create_superuser(
            username='admin.idioma.latam',
            password='SenhaTeste123!',
        )
        cls.superuser.perfil.role = Perfil.Role.ADMIN
        cls.superuser.perfil.save(update_fields=['role'])
        cls.url = reverse('estoque:cadastrar_usuario')

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_modelo_forca_espanhol_para_empresa_latam(self):
        user = User.objects.create_user('latam.modelo', password='SenhaTeste123!')
        perfil = user.perfil
        perfil.role = Perfil.Role.ADMIN
        perfil.empresa = self.latam
        perfil.idioma = Perfil.Idioma.PT_BR
        perfil.save(update_fields=['role', 'empresa', 'idioma'])

        perfil.refresh_from_db()
        self.assertEqual(perfil.idioma, Perfil.Idioma.ES)

    def test_cadastro_latam_define_espanhol_automaticamente(self):
        response = self.client.post(self.url, {
            'username': 'latam.cadastro',
            'password': 'SenhaTeste123!',
            'first_name': 'Usuário LATAM',
            'perfil_acesso': 'admin',
            'empresa': str(self.latam.pk),
            'is_active': 'on',
        })

        self.assertRedirects(response, self.url)
        perfil = User.objects.get(username='latam.cadastro').perfil
        self.assertEqual(perfil.empresa, self.latam)
        self.assertEqual(perfil.idioma, Perfil.Idioma.ES)

    def test_edicao_para_latam_corrige_idioma(self):
        user = User.objects.create_user('usuario.editado', password='SenhaTeste123!')
        user.perfil.role = Perfil.Role.ADMIN
        user.perfil.empresa = self.brasil
        user.perfil.idioma = Perfil.Idioma.EN
        user.perfil.save()

        response = self.client.post(self.url, {
            'usuario_id': str(user.pk),
            'username': user.username,
            'first_name': 'Editado',
            'perfil_acesso': 'admin',
            'empresa': str(self.latam.pk),
            'is_active': 'on',
        })

        self.assertRedirects(response, self.url)
        user.perfil.refresh_from_db()
        self.assertEqual(user.perfil.empresa, self.latam)
        self.assertEqual(user.perfil.idioma, Perfil.Idioma.ES)

    def test_outra_empresa_preserva_idioma_configurado(self):
        user = User.objects.create_user('brasil.idioma', password='SenhaTeste123!')
        perfil = user.perfil
        perfil.role = Perfil.Role.ADMIN
        perfil.empresa = self.brasil
        perfil.idioma = Perfil.Idioma.EN
        perfil.save()

        perfil.refresh_from_db()
        self.assertEqual(perfil.idioma, Perfil.Idioma.EN)

    def test_tela_informa_automacao_apenas_na_latam(self):
        response = self.client.get(self.url)

        self.assertContains(
            response,
            'data-idioma-obrigatorio="es"',
            count=1,
        )
        self.assertContains(
            response,
            'O idioma deste usuário será definido automaticamente como Espanhol.',
        )
