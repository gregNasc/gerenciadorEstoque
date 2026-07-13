from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from estoque.models import Base, Empresa, Perfil
from insumos.constants import GruposInsumos
from insumos.models import ChecklistDiario, Cliente, Inventario


class UltimoChecklistPorLojaTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa teste')
        self.base = Base.objects.create(nome='OXXO SP SUL X', empresa=self.empresa)
        self.outra_base = Base.objects.create(nome='RIO DE JANEIRO', empresa=self.empresa)
        self.admin = User.objects.create_user('admin_teste', password='teste', is_staff=True)
        Perfil.objects.create(user=self.admin, empresa=self.empresa, role=Perfil.Role.ADMIN)
        self.operador = User.objects.create_user('operador_teste', password='teste')
        perfil_operador = Perfil.objects.create(
            user=self.operador,
            empresa=self.empresa,
            role=Perfil.Role.OPERADOR,
        )
        perfil_operador.bases_checklist.add(self.outra_base)
        self.cliente = Cliente.objects.create(sigla='OXX', nome='Mercado OXXO')

        self.inventario_antigo = self._inventario(date(2026, 7, 1))
        self.inventario_recente = self._inventario(date(2026, 7, 5))
        self.inventario_alvo = self._inventario(date(2026, 7, 10))
        self.inventario_outra_base = Inventario.objects.create(
            cliente=self.cliente,
            loja='1105487',
            base=self.outra_base,
            data_inicio=date(2026, 7, 10),
            criado_por=self.admin,
            tipo='T',
        )
        self.checklist_finalizado = self._checklist(
            self.inventario_antigo,
            status='FINALIZADO',
        )
        self.checklist_recente = self._checklist(
            self.inventario_recente,
            status='EM_EXECUCAO',
        )

    def _inventario(self, data_inicio):
        return Inventario.objects.create(
            cliente=self.cliente,
            loja='1105487',
            base=self.base,
            data_inicio=data_inicio,
            criado_por=self.admin,
            tipo='T',
        )

    def _checklist(self, inventario, status):
        return ChecklistDiario.objects.create(
            inventario=inventario,
            data_inicio=timezone.now(),
            criado_por=self.admin,
            responsavel=self.admin,
            status=status,
            finalizado_em=timezone.now() if status == 'FINALIZADO' else None,
            finalizado_por=self.admin if status == 'FINALIZADO' else None,
        )

    def test_usa_o_checklist_imediatamente_anterior(self):
        self.client.force_login(self.admin)

        resposta = self.client.get(
            reverse('insumos:api_ultimo_checklist'),
            {'inventario': self.inventario_alvo.id},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.json()['dados']['checklist_id'],
            self.checklist_recente.id,
        )

    def test_bloqueia_usuario_de_outra_base(self):
        self.client.force_login(self.operador)

        resposta = self.client.get(
            reverse('insumos:api_ultimo_checklist'),
            {'inventario': self.inventario_alvo.id},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_usuario_inicia_vazio_quando_historico_e_de_outra_base(self):
        self.client.force_login(self.operador)

        resposta = self.client.get(
            reverse('insumos:api_ultimo_checklist'),
            {'inventario': self.inventario_outra_base.id},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.json()['dados'])


class AcessoCustosInsumosTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa custos')
        self.admin = self._usuario('admin_custos', Perfil.Role.ADMIN)
        self.gestor = self._usuario('gestor_custos', Perfil.Role.GESTOR)
        self.compras = self._usuario(
            'compras_custos', Perfil.Role.OPERADOR, GruposInsumos.COMPRAS
        )
        self.financeiro = self._usuario(
            'financeiro_custos', Perfil.Role.OPERADOR, GruposInsumos.FINANCEIRO
        )
        self.executivo = self._usuario(
            'executivo_custos', Perfil.Role.OPERADOR, GruposInsumos.EXECUTIVO
        )
        self.urls = [
            reverse('insumos:dashboard_custos'),
            reverse('insumos:precos_insumos'),
            reverse('insumos:fornecedores_insumos'),
        ]

    def _usuario(self, username, role, grupo=None):
        user = User.objects.create_user(username, password='teste')
        Perfil.objects.create(user=user, empresa=self.empresa, role=role)
        if grupo:
            user.groups.add(Group.objects.create(name=grupo))
        return user

    def test_perfis_financeiros_visualizam_as_telas(self):
        for user in (self.admin, self.compras, self.financeiro, self.executivo):
            self.client.force_login(user)
            for url in self.urls:
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_gestor_nao_ve_links_nem_acessa_urls(self):
        self.client.force_login(self.gestor)
        pagina = self.client.get('/')
        self.assertEqual(pagina.status_code, 200)
        for url in self.urls:
            self.assertNotContains(pagina, url)
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(self.urls[1], {}).status_code, 403)

    def test_financeiro_nao_pode_alterar_precos(self):
        self.client.force_login(self.financeiro)
        self.assertEqual(self.client.post(self.urls[1], {}).status_code, 403)

    def test_compras_pode_enviar_formulario_de_preco(self):
        self.client.force_login(self.compras)
        self.assertEqual(self.client.post(self.urls[1], {}).status_code, 200)

    def test_dashboard_aceita_filtros_vazios(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse('insumos:dashboard_custos'), {
            'inicio': '2026-07-01',
            'fim': '2026-07-12',
            'base': '',
            'cliente': '',
            'loja': '',
            'tipo': '',
            'pessoas': '',
            'inventario': '',
        })
        self.assertEqual(resposta.status_code, 200)

    def test_financeiro_visualiza_mas_nao_executa_pesquisa_online(self):
        self.client.force_login(self.financeiro)
        url = reverse('insumos:pesquisa_precos_online')
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
