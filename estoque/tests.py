from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from estoque.models import (
    Base, Comunicado, Empresa, Equipamento, GrupoRegional, Perfil, Produto, Sick,
)
from estoque.services.assistente_operacional_service import AssistenteOperacionalService
from estoque.services.comunicado_service import ComunicadoService
from estoque.services.emprestimo_service import EmprestimoService
from estoque.services.transferencia_services import criar_transferencia
from insumos.models import (
    CategoriaInsumo,
    ChecklistDiario,
    Cliente,
    ConsumoInsumo,
    Insumo,
    Inventario,
    ItemChecklist,
)


class ToryTemposOperacionaisTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Tory')
        self.base = Base.objects.create(nome='SP TORY', empresa=self.empresa)
        self.usuario = User.objects.create_user('tory_admin')
        Perfil.objects.update_or_create(
            user=self.usuario,
            defaults={
                'empresa': self.empresa,
                'role': Perfil.Role.ADMIN,
            },
        )
        self.usuario.refresh_from_db()
        self.cliente = Cliente.objects.create(sigla='OXX', nome='Mercado OXXO')
        self.inventario = Inventario.objects.create(
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
            tipo='T',
            status='FINALIZADO',
        )

    @staticmethod
    def _dt(ano, mes, dia, hora, minuto=0):
        return timezone.make_aware(datetime(ano, mes, dia, hora, minuto))

    def test_responde_duracao_produtividade_e_desvios_sem_jornada_fixa(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Quanto tempo durou o inventário da OXXO loja 58?',
        )

        self.assertEqual(resultado['contexto']['intencao'], 'inventarios_relatorio')
        self.assertIn('Duração total: 10h24', resultado['resposta'])
        self.assertIn('Tempo efetivo de contagem: 8h35', resultado['resposta'])
        self.assertIn('18 min de atraso', resultado['resposta'])
        self.assertIn('42 min depois', resultado['resposta'])
        self.assertIn('635,30 peças por pessoa/hora', resultado['resposta'])

    def test_simula_duas_pessoas_a_mais_com_hipotese_explicita(self):
        primeira = AssistenteOperacionalService.responder(
            self.usuario,
            'Quanto tempo durou o inventário da OXXO loja 58?',
        )
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'E se fossem mais duas pessoas?',
            contexto=primeira['contexto'],
        )

        self.assertIn('com 16 pessoas', resultado['resposta'])
        self.assertIn('9h06', resultado['resposta'])
        self.assertIn('15/07/2026 às 05:24', resultado['resposta'])
        self.assertIn('projeção mantém a produtividade individual observada e é linear', resultado['resposta'])

    def test_lista_encerramentos_depois_do_horario_sem_presumir_janela(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Quais inventários terminaram depois das 6h neste mês?',
        )

        self.assertIn('inventários encerrados depois das 06:00', resultado['resposta'])
        self.assertIn('OXX | 58 | SP TORY', resultado['resposta'])
        self.assertIn('não recebem janelas presumidas', resultado['resposta'])

    def test_calcula_custo_operacional_sem_confundir_com_custo_de_insumos(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Qual foi o custo adicional por ultrapassar o horário do inventário OXXO loja 58?',
        )

        self.assertEqual(resultado['contexto']['intencao'], 'inventarios_relatorio')
        self.assertIn('Custo adicional pelo encerramento após o previsto: R$ 294,00', resultado['resposta'])

    def test_nao_inventa_duracao_quando_timestamps_estao_ausentes(self):
        Inventario.objects.create(
            cliente=self.cliente,
            loja='60',
            base=self.base,
            data_inicio=date(2026, 7, 14),
            criado_por=self.usuario,
            horario_inicio=datetime.strptime('20:00', '%H:%M').time(),
        )

        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Quanto tempo durou o inventário da OXXO loja 60?',
        )

        self.assertIn('Duração total: -', resultado['resposta'])
        self.assertIn('não usa 20h–6h nem qualquer outra jornada fixa', resultado['resposta'])

    def test_sao_paulo_ambiguo_pede_base_com_acoes_clicaveis(self):
        base_sao_paulo = Base.objects.create(nome='SÃO PAULO', empresa=self.empresa)
        Base.objects.create(nome='SP INT BAURU', empresa=self.empresa)
        Base.objects.create(nome='RIO DE JANEIRO', empresa=self.empresa)
        Inventario.objects.create(
            cliente=self.cliente,
            loja='17',
            base=base_sao_paulo,
            data_inicio=date(2026, 7, 15),
            criado_por=self.usuario,
            pessoas=15,
            tipo='T',
        )

        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Quais inventários hoje em São Paulo?',
        )

        self.assertEqual(resultado['categoria'], 'escolher_base')
        self.assertEqual(resultado['contexto']['intencao'], 'inventarios_data_base')
        self.assertEqual(resultado['contexto']['uf'], '')
        labels = [acao['label'] for acao in resultado['acoes']]
        self.assertIn('SÃO PAULO', labels)
        self.assertIn('SP INT BAURU', labels)
        self.assertIn('Todo o estado de SP', labels)
        self.assertNotIn('RIO DE JANEIRO', labels)
        self.assertNotIn('Resumo de inventários', resultado['resposta'])
        self.assertIn('OPÇÃO | ESCOPO CONSULTADO | COMO PEDIR', resultado['resposta'])
        self.assertNotIn('- SP INT BAURU', resultado['resposta'])

        acao_sao_paulo = next(
            acao for acao in resultado['acoes']
            if acao['label'] == 'SÃO PAULO'
        )
        selecionado = AssistenteOperacionalService.responder(
            self.usuario,
            acao_sao_paulo['pergunta'],
            contexto=resultado['contexto'],
        )

        self.assertEqual(selecionado['contexto']['base'], 'SÃO PAULO')
        self.assertEqual(selecionado['contexto']['data'], '2026-07-15')
        self.assertIn('OXX loja 17 | T | 15', selecionado['resposta'])

    def test_quantidade_de_coletores_usa_tabelas_de_status_e_modelo(self):
        produto_a = Produto.objects.create(
            codigo='COL-TORY-A',
            descricao='COLETOR MODELO A',
            fabricante='Fabricante A',
            modelo='A',
            categoria='Coletores',
        )
        produto_b = Produto.objects.create(
            codigo='COL-TORY-B',
            descricao='COLETOR MODELO B',
            fabricante='Fabricante B',
            modelo='B',
            categoria='Coletores',
        )
        for indice, (produto, status) in enumerate((
            (produto_a, 'ATIVO'),
            (produto_a, 'ATIVO'),
            (produto_b, 'INATIVO'),
        ), start=1):
            Equipamento.objects.create(
                produto=produto,
                numero_serie=f'COL-SERIE-{indice}',
                patrimonio=f'COL-PAT-{indice}',
                regional=self.base,
                codigo=f'COL-EQP-{indice}',
                status=status,
            )

        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Quantos coletores existem na base SP TORY?',
        )

        self.assertEqual(resultado['categoria'], 'estoque')
        self.assertIn(
            'TOTAL VISÍVEL | ATIVOS | EM USO | SICK | MANUTENÇÃO | INATIVOS',
            resultado['resposta'],
        )
        self.assertIn('3 | 2 | 0 | 0 | 0 | 1', resultado['resposta'])
        self.assertIn('MODELO/PRODUTO | QUANTIDADE | %', resultado['resposta'])
        self.assertIn('COLETOR MODELO A | 2 | 66,67%', resultado['resposta'])
        self.assertIn('COLETOR MODELO B | 1 | 33,33%', resultado['resposta'])
        self.assertNotIn('Modelos/produtos:', resultado['resposta'])

        resumo_geral = AssistenteOperacionalService.responder(
            self.usuario,
            'Quantos equipamentos existem na base SP TORY?',
        )
        self.assertIn('ESCOPO | TOTAL VISÍVEL', resumo_geral['resposta'])
        self.assertIn('STATUS | QUANTIDADE | %', resumo_geral['resposta'])
        self.assertIn('ATIVO | 2 | 66,67%', resumo_geral['resposta'])
        self.assertIn('INATIVO | 1 | 33,33%', resumo_geral['resposta'])
        self.assertIn('CATEGORIA | QUANTIDADE | %', resumo_geral['resposta'])
        self.assertIn('Coletores | 3 | 100,00%', resumo_geral['resposta'])
        self.assertNotIn('Por status:', resumo_geral['resposta'])
        self.assertNotIn('Por categoria:', resumo_geral['resposta'])

    def test_capacidade_da_base_usa_tabela_de_demanda_e_resultado(self):
        self.inventario.data_inicio = timezone.localdate()
        self.inventario.data_fim = timezone.localdate()
        self.inventario.pessoas = 4
        self.inventario.save(update_fields=('data_inicio', 'data_fim', 'pessoas'))
        produto = Produto.objects.create(
            codigo='COL-CAP-TORY',
            descricao='COLETOR CAPACIDADE TORY',
            fabricante='Fabricante',
            modelo='CAP',
            categoria='Coletores',
        )
        for indice in range(3):
            Equipamento.objects.create(
                produto=produto,
                numero_serie=f'CAP-SERIE-{indice}',
                patrimonio=f'CAP-PAT-{indice}',
                regional=self.base,
                codigo=f'CAP-EQP-{indice}',
                status='ATIVO',
            )

        primeira = AssistenteOperacionalService.responder(
            self.usuario,
            'Quantos coletores existem na base SP TORY?',
        )
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'A base SP TORY atende hoje?',
            contexto=primeira['contexto'],
        )

        self.assertEqual(resultado['categoria'], 'capacidade')
        self.assertIn(
            'INVENTÁRIOS | PESSOAS PREVISTAS | COLETORES CADASTRADOS | COLETORES ATIVOS',
            resultado['resposta'],
        )
        self.assertIn('1 | 4 | 3 | 3', resultado['resposta'])
        self.assertIn('SITUAÇÃO | DIFERENÇA', resultado['resposta'])
        self.assertIn('NÃO ATENDE | Faltam 1 coletor(es)', resultado['resposta'])
        self.assertNotIn('- Pessoas previstas:', resultado['resposta'])

    def test_uf_sp_explicita_consulta_estado_sem_desambiguar(self):
        Base.objects.create(nome='SÃO PAULO', empresa=self.empresa)
        Base.objects.create(nome='SP INT BAURU', empresa=self.empresa)

        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Quais inventários hoje na UF SP?',
        )

        self.assertEqual(resultado['contexto']['uf'], 'SP')
        self.assertEqual(resultado['acoes'], [])

    def test_endpoint_e_pagina_expoem_botoes_clicaveis_de_base(self):
        Base.objects.create(nome='SÃO PAULO', empresa=self.empresa)
        Base.objects.create(nome='SP INT BAURU', empresa=self.empresa)
        self.client.force_login(self.usuario)
        url = reverse('estoque:assistente_operacional')

        ajax = self.client.post(
            url,
            {'pergunta': 'Quais inventários hoje em São Paulo?'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(ajax.status_code, 200)
        self.assertIn(
            {'label': 'SÃO PAULO', 'pergunta': 'Na base SÃO PAULO'},
            ajax.json()['acoes'],
        )

        pagina = self.client.post(
            url,
            {'pergunta': 'Quais inventários hoje em São Paulo?'},
        )
        self.assertContains(pagina, 'value="Na base SÃO PAULO"')
        self.assertContains(pagina, '>SÃO PAULO</button>')

    def test_produtividade_usa_equipe_t_apoio_e_simula_85_pessoas(self):
        cliente_gig = Cliente.objects.create(sigla='GIG', nome='Giga Atacadista')
        dados = [
            (date(2026, 7, 13), 'CA', 4, 22),
            (date(2026, 7, 14), 'CA', 26, 20),
            (date(2026, 7, 14), 'CP', 1, 9),
            (date(2026, 7, 15), 'APOIO', 15, 22),
            (date(2026, 7, 15), 'T', 30, 22),
            (date(2026, 7, 15), 'CP', 1, 9),
        ]
        for data_inicio, tipo, pessoas, hora in dados:
            Inventario.objects.create(
                cliente=cliente_gig,
                loja='903',
                base=self.base,
                data_inicio=data_inicio,
                criado_por=self.usuario,
                pessoas=pessoas,
                tipo=tipo,
                horario_inicio=datetime.strptime(f'{hora:02d}:00', '%H:%M').time(),
                previsao_pecas=2241000 if tipo == 'T' else None,
                prod_media=5000 if tipo == 'T' else None,
            )

        detalhe = AssistenteOperacionalService.responder(
            self.usuario,
            'Fale sobre o GIG 903',
        )
        produtividade = AssistenteOperacionalService.responder(
            self.usuario,
            'produtividade',
            contexto=detalhe['contexto'],
        )

        self.assertIn('Alocações pessoa-etapa: 77', produtividade['resposta'])
        self.assertIn('Equipes de contagem (soma de T + APOIO): 45', produtividade['resposta'])
        self.assertIn('Carga prevista por pessoa da equipe de contagem: 49.800,00', produtividade['resposta'])
        self.assertIn('77 | 45 | 2.241.000 | 5.000,00 | 49.800,00 | 9h58', produtividade['resposta'])

        simulacao = AssistenteOperacionalService.responder(
            self.usuario,
            'com 85 pessoas?',
            contexto=produtividade['contexto'],
        )

        self.assertIn(
            'CENÁRIO | EQUIPE | PREVISÃO DE PEÇAS | PRODUTIVIDADE | DURAÇÃO | INÍCIO | TÉRMINO',
            simulacao['resposta'],
        )
        self.assertIn(
            'Atual | 45 | 2.241.000 | 5.000,00 peças/pessoa/h | 9h58 | '
            '15/07/2026 às 22:00 | 16/07/2026 às 07:57',
            simulacao['resposta'],
        )
        self.assertIn(
            'Simulada | 85 | 2.241.000 | 5.000,00 peças/pessoa/h | 5h16 | '
            '15/07/2026 às 22:00 | 16/07/2026 às 03:16',
            simulacao['resposta'],
        )
        self.assertNotIn('Resumo de inventários', simulacao['resposta'])

    def test_seguimento_reconhece_cliente_e_loja_alfanumerica(self):
        base_rio = Base.objects.create(nome='RIO DE JANEIRO', empresa=self.empresa)
        cliente_hor = Cliente.objects.create(sigla='HOR', nome='Hortifruti')
        Inventario.objects.create(
            cliente=cliente_hor,
            loja='A063',
            base=base_rio,
            data_inicio=date(2026, 7, 15),
            criado_por=self.usuario,
            pessoas=15,
            tipo='T',
            horario_inicio=datetime.strptime('22:00', '%H:%M').time(),
        )

        resumo_rj = AssistenteOperacionalService.responder(
            self.usuario,
            'inventários hoje no RJ',
        )
        detalhe = AssistenteOperacionalService.responder(
            self.usuario,
            'fale sobre HOR A063',
            contexto=resumo_rj['contexto'],
        )

        self.assertEqual(detalhe['contexto']['cliente'], 'HOR')
        self.assertEqual(detalhe['contexto']['loja'], 'a063')
        self.assertEqual(detalhe['contexto']['uf'], 'RJ')
        self.assertIn('detalhamento operacional', detalhe['resposta'])
        self.assertIn('HOR loja A063', detalhe['resposta'])
        self.assertNotIn('Resumo de inventarios (UF RJ', detalhe['resposta'])

    def test_consultas_cotidianas_reconhecem_cliente_e_ranking_de_custos(self):
        cliente_asi = Cliente.objects.create(sigla='ASI', nome='Assaí Atacadista')
        Cliente.objects.create(sigla='POR', nome='Cliente com sigla ambígua')
        base_asi = Base.objects.create(nome='SÃO PAULO', empresa=self.empresa)
        inventario_asi = Inventario.objects.create(
            cliente=cliente_asi,
            loja='17',
            base=base_asi,
            data_inicio=date(2026, 7, 14),
            criado_por=self.usuario,
            pessoas=10,
            tipo='T',
        )
        categoria = CategoriaInsumo.objects.create(nome='Material de escritório')
        insumo = Insumo.objects.create(
            descricao='Papel para teste',
            categoria=categoria,
            unidade_medida='PCT',
            valor_medio=Decimal('10.00'),
        )

        for inventario, quantidade, total in (
            (self.inventario, Decimal('2'), Decimal('20.00')),
            (inventario_asi, Decimal('5'), Decimal('50.00')),
        ):
            checklist = ChecklistDiario.objects.create(
                inventario=inventario,
                data_inicio=self._dt(2026, 7, 14, 20),
                data_fim=self._dt(2026, 7, 15, 5),
                criado_por=self.usuario,
                responsavel=self.usuario,
                status='FINALIZADO',
                finalizado_em=self._dt(2026, 7, 15, 5),
                finalizado_por=self.usuario,
            )
            item = ItemChecklist.objects.create(
                checklist=checklist,
                insumo=insumo,
                quantidade_enviada=quantidade,
                quantidade_utilizada=quantidade,
                status_retorno='CONFERIDO',
            )
            ConsumoInsumo.objects.create(
                inventario=inventario,
                item_checklist=item,
                insumo=insumo,
                quantidade=quantidade,
                valor_unitario=Decimal('10.00'),
                valor_total=total,
            )

        maiores = AssistenteOperacionalService.responder(
            self.usuario,
            'quais os maiores custos',
        )
        self.assertEqual(maiores['contexto']['intencao'], 'custos_insumos')
        self.assertIn('DATA | CLIENTE | LOJA | BASE', maiores['resposta'])
        self.assertNotIn('posso ajudar com perguntas como', maiores['resposta'])

        por_cliente = AssistenteOperacionalService.responder(
            self.usuario,
            'quais os maiores custos por cliente',
        )
        self.assertEqual(por_cliente['contexto']['intencao'], 'custos_insumos')
        self.assertEqual(por_cliente['contexto']['cliente'], '')
        self.assertIn(
            'CLIENTE | INVENTÁRIOS | CUSTO TOTAL | %',
            por_cliente['resposta'],
        )
        self.assertIn('ASI | 1 | R$ 50,00 | 71,43%', por_cliente['resposta'])
        self.assertIn('OXX | 1 | R$ 20,00 | 28,57%', por_cliente['resposta'])
        self.assertNotIn('cliente POR', por_cliente['resposta'])

        por_base = AssistenteOperacionalService.responder(
            self.usuario,
            'quais bases possuem os maiores custos',
            contexto=maiores['contexto'],
        )
        self.assertEqual(por_base['contexto']['intencao'], 'custos_insumos')
        self.assertIn(
            'BASE | INVENTÁRIOS | CUSTO TOTAL | CUSTO MÉDIO/INVENTÁRIO | %',
            por_base['resposta'],
        )
        self.assertIn('SÃO PAULO | 1 | R$ 50,00 | R$ 50,00 | 71,43%', por_base['resposta'])
        self.assertIn('SP TORY | 1 | R$ 20,00 | R$ 20,00 | 28,57%', por_base['resposta'])
        self.assertNotIn('DATA | CLIENTE | LOJA | BASE', por_base['resposta'])

        por_base_no_mes = AssistenteOperacionalService.responder(
            self.usuario,
            'dez bases com maiores custos no mês',
            contexto=por_base['contexto'],
        )
        self.assertIn('BASE | INVENTÁRIOS | CUSTO TOTAL', por_base_no_mes['resposta'])
        self.assertIn('Ranking das 2 bases com maior custo no período', por_base_no_mes['resposta'])

        cliente_por_explicito = AssistenteOperacionalService.responder(
            self.usuario,
            'quais os custos do cliente POR',
        )
        self.assertEqual(cliente_por_explicito['contexto']['cliente'], 'POR')

        cliente = AssistenteOperacionalService.responder(
            self.usuario,
            'fale sobre oxx',
        )
        self.assertEqual(cliente['contexto']['intencao'], 'inventarios_relatorio')
        self.assertEqual(cliente['contexto']['cliente'], 'OXX')
        self.assertIn('resumo de inventários', cliente['resposta'])
        self.assertIn('OXX | 58', cliente['resposta'])


class TransferenciaServiceTests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(nome='Empresa Transferencia')
        self.usuario = User.objects.create_user('operador_transferencia')
        grupo = GrupoRegional.objects.create(
            nome='Grupo Transferencia',
            gestor_principal=self.usuario,
        )
        self.origem = Base.objects.create(
            nome='Origem', empresa=empresa, grupo_regional=grupo,
        )
        self.destino = Base.objects.create(
            nome='Destino', empresa=empresa, grupo_regional=grupo,
        )
        produto = Produto.objects.create(
            codigo='PROD-TRANSF',
            descricao='Coletor de teste',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Coletores',
        )
        self.equipamentos = [
            Equipamento.objects.create(
                produto=produto,
                numero_serie=f'SERIE-{indice}',
                patrimonio=f'PAT-{indice}',
                regional=self.origem,
                codigo=f'EQP-TRANSF-{indice}',
            )
            for indice in range(2)
        ]

    def test_cria_protocolos_unicos_em_transferencias_consecutivas(self):
        primeira = criar_transferencia(
            equipamentos=[self.equipamentos[0]],
            regional_destino=self.destino,
            solicitado_por=self.usuario,
        )
        segunda = criar_transferencia(
            equipamentos=[self.equipamentos[1]],
            regional_destino=self.destino,
            solicitado_por=self.usuario,
        )

        self.assertTrue(primeira.protocolo)
        self.assertTrue(segunda.protocolo)
        self.assertNotEqual(primeira.protocolo, segunda.protocolo)

    @patch(
        'estoque.services.emprestimo_service.'
        'NotificacaoService.emprestimo_aguardando_recebimento'
    )
    @patch(
        'estoque.services.emprestimo_service.'
        'ComunicadoService.emp_item_reservado'
    )
    def test_cria_protocolos_unicos_em_emprestimos_consecutivos(
        self, comunicado_mock, notificacao_mock,
    ):
        primeiro = EmprestimoService.criar(
            self.origem,
            self.destino,
            self.usuario,
            'Teste do primeiro empréstimo',
            date.today(),
            [self.equipamentos[0]],
        )
        segundo = EmprestimoService.criar(
            self.origem,
            self.destino,
            self.usuario,
            'Teste do segundo empréstimo',
            date.today(),
            [self.equipamentos[1]],
        )

        self.assertTrue(primeiro.protocolo)
        self.assertTrue(segundo.protocolo)
        self.assertNotEqual(primeiro.protocolo, segundo.protocolo)
        self.assertLessEqual(len(primeiro.protocolo), 20)


class ComunicadoManutencaoTests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(nome='Empresa manutenção')
        base = Base.objects.create(nome='Base manutenção', empresa=empresa)
        self.admin = User.objects.create_user('admin_manutencao')
        Perfil.objects.update_or_create(
            user=self.admin,
            defaults={'empresa': None, 'role': Perfil.Role.ADMIN},
        )
        self.rafael = User.objects.create_user('rafael.ribeiro')
        Perfil.objects.update_or_create(
            user=self.rafael,
            defaults={'empresa': empresa, 'role': Perfil.Role.OPERADOR},
        )
        produto = Produto.objects.create(
            codigo='PROD-MANUT', descricao='Coletor em manutenção',
            fabricante='Fabricante', modelo='Modelo', categoria='Coletores',
        )
        equipamento = Equipamento.objects.create(
            produto=produto, numero_serie='SERIE-MANUT', patrimonio='PAT-MANUT',
            regional=base, codigo='EQP-MANUT', status='MANUTENCAO',
        )
        self.sick = Sick.objects.create(
            equipamento=equipamento,
            categoria='HARDWARE',
            motivo='Conector danificado',
            previsao_retorno=timezone.localdate() + timedelta(days=1),
            status_final='MANUTENCAO',
            ativo=True,
        )

    def test_notifica_rafael_e_admins_uma_unica_vez_na_vespera(self):
        primeira = ComunicadoService.notificar_manutencoes_previstas()
        segunda = ComunicadoService.notificar_manutencoes_previstas()

        comunicado = Comunicado.objects.get(
            titulo=f'Manutenção prevista para amanhã — SICK #{self.sick.id}'
        )
        self.assertEqual(len(primeira), 1)
        self.assertEqual(len(segunda), 0)
        self.assertSetEqual(
            set(comunicado.usuarios.values_list('username', flat=True)),
            {'admin_manutencao', 'rafael.ribeiro'},
        )
