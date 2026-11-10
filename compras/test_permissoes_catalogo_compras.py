from django.contrib.auth.models import Group, User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from estoque.context_processors import permissoes_especiais
from estoque.models import Empresa, Perfil
from estoque.policies.compras import ComprasAccessPolicy
from insumos.constants import GruposInsumos


class PermissoesCatalogoComprasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa Catálogo Restrito')
        cls.admin = cls._usuario('admin.catalogo', Perfil.Role.ADMIN)
        cls.gestor = cls._usuario('gestor.catalogo', Perfil.Role.GESTOR)
        cls.operador = cls._usuario('operador.catalogo', Perfil.Role.OPERADOR)
        cls.jose = cls._usuario('jose.barboza', Perfil.Role.ADMIN)
        cls.superuser = cls._usuario('super.catalogo', Perfil.Role.GESTOR)
        cls.superuser.is_superuser = True
        cls.superuser.is_staff = True
        cls.superuser.save(update_fields=['is_superuser', 'is_staff'])
        grupo_compras, _ = Group.objects.get_or_create(name=GruposInsumos.COMPRAS)
        cls.operador.groups.add(grupo_compras)

    @classmethod
    def _usuario(cls, username, role):
        usuario = User.objects.create_user(username, password='Teste123!')
        usuario.perfil.empresa = cls.empresa
        usuario.perfil.role = role
        usuario.perfil.save(update_fields=['empresa', 'role'])
        return usuario

    def test_politica_permite_somente_superuser(self):
        self.assertTrue(
            ComprasAccessPolicy.pode_gerenciar_catalogo_compras(self.superuser)
        )
        for usuario in (self.admin, self.gestor, self.operador, self.jose):
            with self.subTest(usuario=usuario.username):
                self.assertFalse(
                    ComprasAccessPolicy.pode_gerenciar_catalogo_compras(usuario)
                )

    def test_rotas_bloqueiam_admin_gestor_operador_e_jose(self):
        rotas = (
            reverse('compras:catalogo_empresa'),
            reverse('compras:criar_produto_catalogo'),
        )
        for usuario in (self.admin, self.gestor, self.operador, self.jose):
            self.client.force_login(usuario)
            for rota in rotas:
                with self.subTest(usuario=usuario.username, rota=rota):
                    self.assertEqual(self.client.get(rota).status_code, 403)

    def test_rotas_permanecem_disponiveis_para_superuser(self):
        self.client.force_login(self.superuser)
        self.assertEqual(
            self.client.get(reverse('compras:catalogo_empresa')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('compras:criar_produto_catalogo')).status_code,
            200,
        )

    def test_contexto_oculta_aba_sem_retirar_cadastro_operacional_do_gestor(self):
        for usuario in (self.gestor, self.operador, self.jose):
            requisicao = RequestFactory().get('/')
            requisicao.user = usuario
            contexto = permissoes_especiais(requisicao)
            with self.subTest(usuario=usuario.username):
                self.assertFalse(
                    contexto['pode_gerenciar_catalogo_compras']
                )
        self.assertTrue(ComprasAccessPolicy.pode_gerenciar_catalogo(self.gestor))

        requisicao = RequestFactory().get('/')
        requisicao.user = self.admin
        self.assertFalse(
            permissoes_especiais(requisicao)['pode_gerenciar_catalogo_compras']
        )

    def test_perfil_compras_recebe_fluxo_unificado_sem_catalogo_administrativo(self):
        self.client.force_login(self.operador)

        for rota in (
            reverse('compras:aquisicao_lista'),
            reverse('compras:remessa_lista'),
        ):
            with self.subTest(rota=rota):
                resposta = self.client.get(rota)
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, 'Compras e suprimentos')
                self.assertContains(resposta, 'Solicitações e cotações')
                self.assertContains(resposta, 'Aquisições')
                self.assertContains(resposta, 'Remessas')
                self.assertContains(resposta, 'Fornecedores')
                self.assertNotContains(
                    resposta,
                    reverse('compras:catalogo_empresa'),
                )
                self.assertNotContains(resposta, 'id="dropdownSolicitacoes"')
                self.assertContains(resposta, 'id="comprasDropdown"')
