from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from estoque.models import Base, Empresa, Perfil
from insumos.constants import GruposInsumos
from insumos.models import (
    CategoriaInsumo,
    ChecklistDiario,
    Cliente,
    Insumo,
    Inventario,
    MovimentacaoInsumo,
    ItemSolicitacaoInsumo,
    SolicitacaoInsumo,
)


class SolicitacaoInsumoFluxoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa solicitações')
        self.base = Base.objects.create(nome='BASE SOLICITAÇÕES', empresa=self.empresa)
        self.admin = self._usuario('admin_solicitacoes', Perfil.Role.ADMIN)
        self.gestor = self._usuario('gestor_solicitacoes', Perfil.Role.GESTOR)
        self.outro_gestor = self._usuario('outro_gestor', Perfil.Role.GESTOR)
        self.gestor.perfil.regionais.add(self.base)
        self.outro_gestor.perfil.regionais.add(self.base)
        categoria = CategoriaInsumo.objects.create(nome='Categoria solicitações')
        self.insumo = Insumo.objects.create(
            descricao='Lacre operacional', categoria=categoria,
            unidade_medida='UN', estoque_minimo=Decimal('5.00'),
        )

    def _usuario(self, username, role):
        user = User.objects.create_user(username, password='teste')
        Perfil.objects.update_or_create(
            user=user,
            defaults={'empresa': self.empresa, 'role': role},
        )
        user.refresh_from_db()
        return user

    def _solicitacao(self, usuario, status='PENDENTE', protocolo='INS-TESTE'):
        solicitacao = SolicitacaoInsumo.objects.create(
            protocolo=protocolo,
            base=self.base,
            solicitante=usuario,
            status=status,
            prioridade='MEDIA',
            justificativa='Conteúdo operacional do pedido.',
            observacao_aprovacao='Análise interna de Compras.',
        )
        ItemSolicitacaoInsumo.objects.create(
            solicitacao=solicitacao,
            insumo=self.insumo,
            quantidade=Decimal('7.50'),
        )
        return solicitacao

    def test_gestor_ve_apenas_status_e_conteudo_do_proprio_pedido(self):
        propria = self._solicitacao(self.gestor, protocolo='INS-PROPRIA')
        alheia = self._solicitacao(self.outro_gestor, protocolo='INS-ALHEIA')
        self.client.force_login(self.gestor)

        lista = self.client.get(reverse('insumos:lista_solicitacoes_insumo'))
        detalhe = self.client.get(reverse(
            'insumos:detalhe_solicitacao', args=[propria.pk],
        ))
        detalhe_alheio = self.client.get(reverse(
            'insumos:detalhe_solicitacao', args=[alheia.pk],
        ))

        self.assertContains(lista, 'INS-PROPRIA')
        self.assertNotContains(lista, 'INS-ALHEIA')
        self.assertNotContains(lista, '<th>Solicitante</th>', html=True)
        self.assertContains(detalhe, 'Conteúdo operacional do pedido.')
        self.assertContains(detalhe, propria.get_status_display())
        self.assertNotContains(detalhe, 'Análise interna de Compras.')
        self.assertEqual(detalhe_alheio.status_code, 404)

    def test_usuario_autorizado_finaliza_solicitacao_em_compra(self):
        solicitacao = self._solicitacao(
            self.gestor, status='EM_COMPRA', protocolo='INS-FINALIZAR',
        )
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse('insumos:decidir_solicitacao', args=[solicitacao.pk]),
            {'acao': 'finalizar', 'observacao': 'Material recebido e conferido.'},
        )

        solicitacao.refresh_from_db()
        item = solicitacao.itens.get()
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(solicitacao.status, 'FINALIZADA')
        self.assertEqual(solicitacao.finalizado_por, self.admin)
        self.assertIsNotNone(solicitacao.finalizado_em)
        self.assertEqual(item.quantidade_atendida, item.quantidade)

    def test_gestor_nao_pode_finalizar(self):
        solicitacao = self._solicitacao(
            self.gestor, status='EM_COMPRA', protocolo='INS-BLOQUEADA',
        )
        self.client.force_login(self.gestor)
        resposta = self.client.post(
            reverse('insumos:decidir_solicitacao', args=[solicitacao.pk]),
            {'acao': 'finalizar'},
        )
        solicitacao.refresh_from_db()
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(solicitacao.status, 'EM_COMPRA')


class EstoqueInsumosDesempenhoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa estoque rápido')
        self.base = Base.objects.create(nome='BASE ESTOQUE RÁPIDO', empresa=self.empresa)
        self.admin = User.objects.create_user('admin_estoque_rapido', password='teste')
        Perfil.objects.update_or_create(
            user=self.admin,
            defaults={'empresa': None, 'role': Perfil.Role.ADMIN},
        )
        self.admin.refresh_from_db()
        categoria = CategoriaInsumo.objects.create(nome='Categoria estoque rápido')
        self.critico = Insumo.objects.create(
            descricao='Item crítico', categoria=categoria, unidade_medida='UN',
            estoque_minimo=Decimal('5.00'),
        )
        self.ok = Insumo.objects.create(
            descricao='Item normal', categoria=categoria, unidade_medida='UN',
            estoque_minimo=Decimal('2.00'),
        )
        for insumo, quantidade in (
            (self.critico, Decimal('4.00')),
            (self.ok, Decimal('3.00')),
        ):
            MovimentacaoInsumo.objects.create(
                base=self.base, insumo=insumo, tipo='ENTRADA',
                quantidade=quantidade, valor_unitario=Decimal('1.00'),
                usuario=self.admin,
            )
        self.client.force_login(self.admin)

    def test_tela_agrega_saldos_e_renderiza_um_unico_formulario(self):
        sem_base = self.client.get(reverse('insumos:estoque_insumos'))
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(
                reverse('insumos:estoque_insumos'),
                {'base': self.base.pk},
            )

        por_item = {
            item['insumo'].descricao: item
            for item in resposta.context['estoque']
        }
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(sem_base.context['aguardando_filtro_base'])
        self.assertEqual(sem_base.context['estoque'], [])
        self.assertLess(len(sem_base.content), 250000)
        self.assertLess(len(consultas), 30)
        self.assertTrue(por_item['Item crítico']['critico'])
        self.assertFalse(por_item['Item normal']['critico'])
        self.assertContains(resposta, 'id="formAjusteEstoque"', count=1)
        self.assertNotContains(resposta, 'data-ajuste-row')
        self.assertNotContains(resposta, 'modalAjusteEstoque')
        self.assertContains(resposta, 'data-estoque-filter="criticos"')
        self.assertContains(resposta, 'data-estoque-action="base"')

    def test_estoque_minimo_aceita_decimal_ate_dez(self):
        self.critico.estoque_minimo = Decimal('2.50')
        self.critico.full_clean()
        self.critico.estoque_minimo = Decimal('10.01')
        with self.assertRaises(ValidationError):
            self.critico.full_clean()


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


class FiltroValorEstoqueCustosTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa filtro estoque')
        self.base_a = Base.objects.create(nome='BASE CUSTO A', empresa=self.empresa)
        self.base_b = Base.objects.create(nome='BASE CUSTO B', empresa=self.empresa)
        self.admin = User.objects.create_user('admin_filtro_estoque')
        Perfil.objects.update_or_create(
            user=self.admin,
            defaults={'empresa': None, 'role': Perfil.Role.ADMIN},
        )
        categoria = CategoriaInsumo.objects.create(nome='Categoria filtro estoque')
        self.insumo = Insumo.objects.create(
            descricao='Insumo filtro estoque',
            categoria=categoria,
            unidade_medida='UN',
            valor_medio=Decimal('10.00'),
        )
        MovimentacaoInsumo.objects.create(
            base=self.base_a,
            insumo=self.insumo,
            tipo='ENTRADA',
            quantidade=Decimal('10'),
            valor_unitario=Decimal('10'),
            usuario=self.admin,
        )
        MovimentacaoInsumo.objects.create(
            base=self.base_b,
            insumo=self.insumo,
            tipo='ENTRADA',
            quantidade=Decimal('20'),
            valor_unitario=Decimal('10'),
            usuario=self.admin,
        )
        self.client.force_login(self.admin)

    def test_valor_estimado_do_estoque_respeita_base_selecionada(self):
        url = reverse('insumos:dashboard_custos')

        todas = self.client.get(url)
        apenas_base_a = self.client.get(url, {'base': self.base_a.pk})
        apenas_base_b = self.client.get(url, {'base': self.base_b.pk})

        self.assertEqual(todas.context['valor_estoque'], Decimal('300.00'))
        self.assertEqual(apenas_base_a.context['valor_estoque'], Decimal('100.00'))
        self.assertEqual(apenas_base_b.context['valor_estoque'], Decimal('200.00'))


class MetricasOperacionaisInventarioTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa operacional')
        self.base = Base.objects.create(nome='SP OPERACIONAL', empresa=self.empresa)
        self.usuario = User.objects.create_user('planejamento_teste')
        Perfil.objects.update_or_create(
            user=self.usuario,
            defaults={
                'empresa': self.empresa,
                'role': Perfil.Role.ADMIN,
            },
        )
        self.cliente = Cliente.objects.create(sigla='OXX', nome='Mercado OXXO')

    @staticmethod
    def _dt(ano, mes, dia, hora, minuto=0):
        return timezone.make_aware(datetime(ano, mes, dia, hora, minuto))

    def test_calcula_duracoes_produtividade_e_custo_com_timestamps_reais(self):
        inventario = Inventario.objects.create(
            cliente=self.cliente,
            loja='58',
            base=self.base,
            data_inicio=date(2026, 7, 14),
            data_fim=date(2026, 7, 15),
            criado_por=self.usuario,
            inicio_previsto=self._dt(2026, 7, 14, 20),
            fim_previsto=self._dt(2026, 7, 15, 6),
            inicio_real=self._dt(2026, 7, 14, 20, 18),
            fim_real=self._dt(2026, 7, 15, 6, 42),
            inicio_contagem=self._dt(2026, 7, 14, 20, 45),
            fim_contagem=self._dt(2026, 7, 15, 5, 20),
            pessoas=14,
            total_pecas=92500,
            custo_hora_pessoa=Decimal('30.00'),
        )

        self.assertAlmostEqual(inventario.duracao_total_horas, 10.4)
        self.assertAlmostEqual(inventario.duracao_contagem_horas, 8 + 35 / 60)
        self.assertAlmostEqual(inventario.tempo_improdutivo_horas, 1 + 49 / 60)
        self.assertEqual(inventario.atraso_inicio_minutos, 18)
        self.assertEqual(inventario.desvio_fim_minutos, 42)
        self.assertAlmostEqual(inventario.produtividade_pessoa_hora, 635.3022, places=3)
        self.assertAlmostEqual(inventario.custo_adicional_atraso, 294)

    def test_aceita_inventario_diurno_e_rejeita_intervalo_invertido(self):
        inventario = Inventario(
            cliente=self.cliente,
            loja='59',
            base=self.base,
            data_inicio=date(2026, 7, 14),
            criado_por=self.usuario,
            inicio_real=self._dt(2026, 7, 14, 8),
            fim_real=self._dt(2026, 7, 14, 16, 30),
        )
        inventario.full_clean()
        self.assertAlmostEqual(inventario.duracao_total_horas, 8.5)

        inventario.fim_real = self._dt(2026, 7, 14, 7, 59)
        with self.assertRaises(ValidationError):
            inventario.full_clean()
