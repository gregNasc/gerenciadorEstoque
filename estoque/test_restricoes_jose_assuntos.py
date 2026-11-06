from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from estoque.context_processors import permissoes_especiais
from estoque.models import Base, Comunicado, Empresa, Perfil
from estoque.policies.compras import ComprasAccessPolicy
from estoque.services.comunicacoes.dispatcher import ComunicacaoDispatcher
from estoque.services.comunicado_service import ComunicadoService


class RestricoesAssuntosJoseBarbozaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(nome='Empresa restrições José')
        cls.base = Base.objects.create(nome='Base restrições José', empresa=cls.empresa)
        cls.jose = User.objects.create_user(
            'jose.barboza', email='jose@example.com', password='Teste123!',
        )
        cls.admin = User.objects.create_user(
            'admin.restricoes', email='admin@example.com', password='Teste123!',
        )
        for user in (cls.jose, cls.admin):
            user.perfil.empresa = cls.empresa
            user.perfil.role = Perfil.Role.ADMIN
            user.perfil.save()

    def test_rotas_e_menu_bloqueiam_assuntos_mas_preservam_catalogo(self):
        self.assertTrue(ComprasAccessPolicy.pode_gerenciar_catalogo(self.jose))
        self.assertFalse(ComprasAccessPolicy.pode_identificar_recebimentos(self.jose))
        request = RequestFactory().get('/')
        request.user = self.jose
        context = permissoes_especiais(request)
        self.assertFalse(context['pode_visualizar_planejamento'])
        self.assertFalse(context['pode_identificar_recebimentos'])
        self.assertFalse(context['pode_visualizar_custodias'])

        self.client.force_login(self.jose)
        for url in (
            reverse('insumos:dashboard_planejamento'),
            reverse('insumos:exportar_planejamento'),
            reverse('compras:individualizacao_pendentes'),
            reverse('estoque:lista_custodias'),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_comunicados_bloqueados_nao_entram_na_central_nem_no_email(self):
        casos = (
            ('Planejamento de consumo atualizado', {}, ''),
            ('Custódia registrada', {'evento_custodia': 'CUSTODIA_CRIADA'}, ''),
            ('Recebimento concluído', {'evento': 'REMESSA_CONFERIDA'}, ''),
            ('Tabela de preços atualizada', {'conteudo_financeiro': True}, ''),
        )
        for indice, (titulo, dados, mensagem) in enumerate(casos):
            with self.subTest(titulo=titulo):
                comunicado = ComunicadoService.criar_acao(
                    titulo=titulo,
                    mensagem=mensagem or f'Mensagem bloqueada {indice}',
                    usuario=self.admin,
                    usuarios=[self.jose],
                    empresa=self.empresa,
                    incluir_admins=False,
                    incluir_autor=False,
                    dados=dados,
                )
                self.assertFalse(comunicado.usuarios.filter(pk=self.jose.pk).exists())
                ComunicacaoDispatcher.criar_entregas(comunicado.pk)
                self.assertFalse(comunicado.entregas.filter(usuario=self.jose).exists())

    def test_comunicado_operacional_nao_relacionado_continua_permitido(self):
        comunicado = ComunicadoService.criar_acao(
            titulo='Equipamento cadastrado',
            mensagem='Um equipamento foi cadastrado na Base.',
            usuario=self.admin,
            usuarios=[self.jose],
            empresa=self.empresa,
            incluir_admins=False,
            incluir_autor=False,
            dados={'evento': 'EQUIPAMENTO_CADASTRADO'},
        )

        self.assertTrue(comunicado.usuarios.filter(pk=self.jose.pk).exists())
        ComunicacaoDispatcher.criar_entregas(comunicado.pk)
        self.assertTrue(comunicado.entregas.filter(usuario=self.jose).exists())

    def test_dispatcher_remove_destinatario_legado_antes_da_entrega(self):
        comunicado = Comunicado.objects.create(
            titulo='Identificar recebimentos',
            mensagem='Há itens aguardando identificação.',
            tipo='OPERACIONAL',
            criado_por=self.admin,
            empresa=self.empresa,
            dados={'evento': 'EQUIPAMENTO_INDIVIDUALIZADO'},
        )
        comunicado.usuarios.add(self.jose)

        ComunicacaoDispatcher.criar_entregas(comunicado.pk)

        self.assertFalse(comunicado.usuarios.filter(pk=self.jose.pk).exists())
        self.assertFalse(comunicado.entregas.filter(usuario=self.jose).exists())
