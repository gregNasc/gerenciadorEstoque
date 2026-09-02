from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from estoque.models import (
    Base, Comunicado, DivergenciaTransferencia, Empresa, Emprestimo,
    Equipamento, GrupoRegional, ItemEmprestimo, PendenciaTransferencia, Perfil,
    Historico, Produto, Sick, Transferencia, TransferenciaItem,
)
from estoque.services.assistente_operacional_service import AssistenteOperacionalService
from estoque.services.assistente.response_builder import construir_erro, construir_resposta
from estoque.services.comunicado_service import ComunicadoService
from estoque.policies.compras import GruposCorporativos
from estoque.services.emprestimo_service import EmprestimoService
from estoque.services.transferencia_services import (
    criar_transferencia,
    enviar_transferencia,
    receber_transferencia,
)
from insumos.models import (
    CategoriaInsumo,
    ChecklistEquipamento,
    ChecklistDiario,
    Cliente,
    ConsumoInsumo,
    Insumo,
    Inventario,
    ItemChecklist,
    LoteTag,
    MovimentacaoInsumo,
)


class ChecklistModalMarkupTests(SimpleTestCase):
    def test_fechar_modal_nao_envia_formulario(self):
        html = render_to_string(
            'estoque/checklist.html',
            {
                'editando': False,
                'inventarios': [],
                'lotes_tags': [],
            },
        )

        self.assertIn(
            '<button type="button" aria-label="Fechar" '
            'onclick="fecharModal()">&times;</button>',
            html,
        )
        self.assertIn(
            '<button type="button" onclick="confirmarSelecao()">Confirmar</button>',
            html,
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
        with patch(
            'estoque.services.assistente_operacional_service.timezone.localdate',
            return_value=date(2026, 7, 15),
        ):
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

    @patch(
        'estoque.services.assistente_operacional_service.timezone.localdate',
        return_value=date(2026, 7, 15),
    )
    def test_sao_paulo_ambiguo_pede_base_com_acoes_clicaveis(self, _localdate_mock):
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

    @patch(
        'estoque.services.assistente_operacional_service.timezone.localdate',
        return_value=date(2026, 7, 14),
    )
    def test_inventarios_hoje_pede_fonte_sem_herdar_cliente_antigo(self, _localdate_mock):
        cliente_antigo = Cliente.objects.create(sigla='BOM', nome='ATACABOM')
        contexto_antigo = {
            'intencao': 'inventarios_relatorio',
            'base': self.base.nome,
            'cliente': cliente_antigo.sigla,
            'loja': '999',
            'pessoas_filtro': 50,
            'tipo_inventario': 'PARCIAL',
        }

        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Bom dia, quais inventários hoje?',
            contexto=contexto_antigo,
        )

        self.assertEqual(resultado['categoria'], 'esclarecimento')
        self.assertEqual(resultado['contexto']['intencao'], 'esclarecer_inventarios')
        self.assertEqual(resultado['contexto']['cliente'], '')
        self.assertEqual(resultado['contexto']['loja'], '')
        self.assertIsNone(resultado['contexto']['pessoas_filtro'])
        self.assertEqual(resultado['contexto']['tipo_inventario'], '')
        self.assertEqual(
            [acao['label'] for acao in resultado['acoes']],
            ['Planejamento de hoje', 'Execução local de hoje'],
        )

        local = AssistenteOperacionalService.responder(
            self.usuario,
            resultado['acoes'][1]['pergunta'],
            contexto=resultado['contexto'],
        )
        self.assertEqual(local['contexto']['intencao'], 'inventarios_data_base')
        self.assertEqual(local['contexto']['cliente'], '')
        self.assertIn('OXX loja 58', local['resposta'])

    @patch(
        'estoque.services.assistente_operacional_service.timezone.localdate',
        return_value=date(2026, 7, 14),
    )
    def test_inventarios_locais_hoje_nao_pede_esclarecimento(self, _localdate_mock):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Mostre os inventários locais de hoje',
        )

        self.assertEqual(resultado['contexto']['intencao'], 'inventarios_data_base')
        self.assertIn('OXX loja 58', resultado['resposta'])

    @patch(
        'estoque.services.assistente_operacional_service.timezone.localdate',
        return_value=date(2026, 7, 14),
    )
    def test_lista_completa_fica_disponivel_para_paginacao(self, _localdate_mock):
        for numero in range(59, 72):
            Inventario.objects.create(
                cliente=self.cliente,
                loja=str(numero),
                base=self.base,
                data_inicio=date(2026, 7, 14),
                criado_por=self.usuario,
                pessoas=5,
                tipo='T',
            )

        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Mostre os inventários locais de hoje',
        )
        envelope = construir_resposta(resultado)
        tabela = next(
            item for item in envelope['componentes']
            if item['tipo'] == 'tabela'
        )

        self.assertEqual(len(tabela['registros']), 14)
        self.assertEqual(tabela['titulo'], 'Inventários encontrados')
        self.assertEqual(tabela['rotulo_total'], 'inventários exibidos')

    @patch(
        'estoque.services.planning_assistant_service.PlanningAssistantService.respond',
        return_value={
            'categoria': 'planejamento',
            'resposta': 'Eventos PAI e FILHO. Evento PAI com dois eventos FILHO.',
            'acoes': [
                {'label': 'Ver PAI/FILHO', 'pergunta': 'Mostre os eventos PAI e FILHO'},
            ],
        },
    )
    def test_resposta_nao_expoe_terminologia_interna_de_hierarquia(self, _respond_mock):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Quais inventários estão planejados para amanhã?',
        )

        conteudo_visivel = ' '.join([
            resultado['resposta'],
            *[acao['label'] for acao in resultado['acoes']],
            *[acao['pergunta'] for acao in resultado['acoes']],
        ])
        self.assertNotRegex(conteudo_visivel.lower(), r'\b(?:pai|filhos?)\b')

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

    @patch(
        'estoque.services.assistente_operacional_service.timezone.localdate',
        return_value=date(2026, 7, 15),
    )
    def test_consultas_cotidianas_reconhecem_cliente_e_ranking_de_custos(self, _localdate):
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
        self.usuario.perfil.role = Perfil.Role.GESTOR
        self.usuario.perfil.empresa = empresa
        self.usuario.perfil.save(update_fields=['role', 'empresa'])
        self.usuario.perfil.regionais.add(self.origem, self.destino)
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

    def test_recebimento_atualiza_itens_e_gera_comunicados(self):
        transferencia = criar_transferencia(
            equipamentos=self.equipamentos,
            regional_destino=self.destino,
            solicitado_por=self.usuario,
        )
        enviar_transferencia(transferencia, self.usuario)
        self.assertFalse(
            transferencia.itens.exclude(status='ENVIADO').exists()
        )
        receber_transferencia(transferencia, self.usuario)

        transferencia.refresh_from_db()
        self.assertEqual(transferencia.status, 'CONCLUIDA')
        self.assertFalse(
            transferencia.itens.exclude(status='RECEBIDO').exists()
        )
        self.assertTrue(
            Comunicado.objects.filter(
                titulo__iexact=f'Transferência {transferencia.protocolo} recebida'
            ).exists()
        )

    def test_visualizacao_exibe_status_divergencia_e_tratativa(self):
        transferencia = criar_transferencia(
            equipamentos=[self.equipamentos[0]],
            regional_destino=self.destino,
            solicitado_por=self.usuario,
        )
        item = transferencia.itens.get()
        item.status = 'DIVERGENTE'
        item.save(update_fields=['status'])
        DivergenciaTransferencia.objects.create(
            transferencia=transferencia,
            item=item,
            equipamento_enviado=item.equipamento,
            serie_recebida='SERIE-DIVERGENTE',
            patrimonio_recebido='PAT-DIVERGENTE',
            observacao='Segregar e validar fotografia com a origem.',
        )
        PendenciaTransferencia.objects.create(
            transferencia=transferencia,
            item=item,
            tipo='DIVERGENCIA',
            patrimonio_esperado=item.equipamento.patrimonio,
            serie_esperada=item.equipamento.numero_serie,
            patrimonio_recebido='PAT-DIVERGENTE',
            serie_recebida='SERIE-DIVERGENTE',
            descricao='Aguardar conferência da etiqueta física.',
            criado_por=self.usuario,
            equipamento=item.equipamento,
            motivo='IDENTIFICACAO_DIVERGENTE',
        )

        self.client.force_login(self.usuario)
        response = self.client.get(
            reverse('estoque:transferencia_selecionados', args=[transferencia.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, transferencia.protocolo)
        self.assertContains(response, 'Divergente')
        self.assertContains(response, 'SERIE-DIVERGENTE')
        self.assertContains(response, 'AGUARDAR CONFERÊNCIA DA ETIQUETA FÍSICA.')

class EmprestimoComPendenciaTests(TestCase):
    def setUp(self):
        empresa = Empresa.objects.create(nome='Empresa Emprestimo Pendente')
        self.usuario = User.objects.create_user('gestor_emprestimo_pendente')
        grupo = GrupoRegional.objects.create(
            nome='Grupo Emprestimo Pendente',
            gestor_principal=self.usuario,
        )
        self.origem = Base.objects.create(
            nome='Origem Emprestimo', empresa=empresa, grupo_regional=grupo,
        )
        self.destino = Base.objects.create(
            nome='Destino Emprestimo', empresa=empresa, grupo_regional=grupo,
        )
        produto = Produto.objects.create(
            codigo='PROD-EMP-PEND',
            descricao='Coletor emprestado',
            fabricante='Fabricante',
            modelo='Modelo',
            categoria='Coletores',
        )
        self.equipamentos = [
            Equipamento.objects.create(
                produto=produto,
                numero_serie=f'SER-EMP-PEND-{indice}',
                patrimonio=f'PAT-EMP-PEND-{indice}',
                regional=self.origem,
                codigo=f'EQP-EMP-PEND-{indice}',
            )
            for indice in range(2)
        ]

    def test_devolucao_incompleta_comunica_divergencia_sem_finalizar(self):
        with patch(
            'estoque.services.emprestimo_service.'
            'NotificacaoService.emprestimo_aguardando_recebimento'
        ):
            emprestimo = EmprestimoService.criar(
                self.origem,
                self.destino,
                self.usuario,
                'Apoio operacional',
                date.today(),
                self.equipamentos,
            )

        ids = [str(item.id) for item in emprestimo.itens.all()]
        EmprestimoService.receber(emprestimo, ids, self.usuario)
        EmprestimoService.devolver(emprestimo, ids[:1], self.usuario)
        EmprestimoService.confirmar_devolucao(
            emprestimo,
            ids[:1],
            self.usuario,
        )

        emprestimo.refresh_from_db()
        self.assertEqual(emprestimo.status, 'EMPRESTADO')
        self.assertTrue(
            Comunicado.objects.filter(
                titulo__iexact='Divergencia no emprestimo',
                mensagem__contains=emprestimo.protocolo,
            ).exists()
        )
        self.assertFalse(
            Comunicado.objects.filter(
                titulo__iexact='Emprestimo finalizado',
                mensagem__contains=emprestimo.regional_origem.nome,
            ).exists()
        )

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
        grupo, _ = Group.objects.get_or_create(name=GruposCorporativos.SICK_MANUTENCAO)
        self.rafael.groups.add(grupo)
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
            titulo__iexact=f'Manutenção prevista para amanhã — SICK #{self.sick.id}'
        )
        self.assertEqual(len(primeira), 1)
        self.assertEqual(len(segunda), 0)
        self.assertSetEqual(
            set(comunicado.usuarios.values_list('username', flat=True)),
            {'admin_manutencao', 'rafael.ribeiro'},
        )

class ToryResponseBuilderTests(TestCase):
    def test_converte_resposta_legada_com_tabela_em_componentes(self):
        resposta = construir_resposta({
            'categoria': 'estoque',
            'resposta': (
                'Foram encontrados 2 equipamentos.\n'
                'PATRIMÔNIO | BASE\n'
                '12345 | Campinas\n'
                '12346 | Sorocaba'
            ),
            'acoes': [{'label': 'Na base Campinas', 'pergunta': 'Na base Campinas'}],
        })

        self.assertTrue(resposta['sucesso'])
        self.assertEqual(resposta['tipo'], 'agrupamento')
        self.assertEqual(resposta['metadados']['total'], 2)
        tabela = next(item for item in resposta['componentes'] if item['tipo'] == 'tabela')
        self.assertEqual(tabela['titulo'], 'Equipamentos encontrados')
        self.assertEqual(tabela['rotulo_total'], 'equipamentos exibidos')
        self.assertEqual(tabela['registros'][0]['PATRIMÔNIO'], '12345')
        self.assertEqual(
            tabela['registros'][0]['_acoes_celulas']['BASE']['pergunta'],
            'Na base Campinas',
        )
        self.assertEqual(
            resposta['acoes'][0],
            {'label': 'Na base Campinas', 'pergunta': 'Na base Campinas'},
        )

    def test_preserva_componentes_estruturados_validos(self):
        resposta = construir_resposta({
            'mensagem': 'Existem 42 equipamentos em SICK.',
            'tipo': 'agrupamento',
            'componentes': [
                {'tipo': 'indicador', 'titulo': 'Equipamentos em SICK', 'valor': 42},
                {
                    'tipo': 'lista',
                    'titulo': 'Por categoria',
                    'itens': [{'nome': 'Coletores', 'valor': 18}],
                },
                {'tipo': 'desconhecido', 'valor': 'ignorado'},
            ],
        })

        self.assertEqual(len(resposta['componentes']), 2)
        self.assertEqual(resposta['componentes'][0]['valor'], 42)
        self.assertEqual(resposta['resposta'], resposta['mensagem'])

    def test_cria_drill_down_controlado_para_loja_de_inventario(self):
        resposta = construir_resposta({
            'resposta': (
                'Inventários encontrados:\n'
                'CLIENTE | LOJA | BASE | STATUS\n'
                'OXX | 58 | SP SUL | PLANEJADO'
            ),
        })

        tabela = next(item for item in resposta['componentes'] if item['tipo'] == 'tabela')
        acoes = tabela['registros'][0]['_acoes_celulas']
        self.assertEqual(
            acoes['LOJA']['pergunta'],
            'Fale sobre o inventário OXX loja 58',
        )
        self.assertEqual(acoes['BASE']['pergunta'], 'Na base SP SUL')

    def test_nomeia_tabelas_de_capacidade_sem_resultado_generico(self):
        resposta = construir_resposta({
            'categoria': 'capacidade',
            'resposta': (
                'Análise operacional de SÃO PAULO em 27/07/2026\n'
                'INVENTÁRIO | TIPOS | PESSOAS | STATUS\n'
                'OXX loja 58 | T | 15 | PLANEJADO\n\n'
                'Demanda total: 15 pessoa(s)\n'
                'Resultado para coletores: ATENDE\n\n'
                'CATEGORIA | PRODUTO | ATIVOS | EM USO | MANUTENÇÃO | TOTAL\n'
                'Coletores | MC65 | 20 | 0 | 1 | 21'
            ),
        })

        tabelas = [
            item for item in resposta['componentes']
            if item['tipo'] == 'tabela'
        ]
        self.assertEqual(tabelas[0]['titulo'], 'Inventários considerados na análise')
        self.assertEqual(tabelas[0]['rotulo_total'], 'inventários analisados')
        self.assertEqual(tabelas[1]['titulo'], 'Equipamentos contabilizados por produto')
        self.assertEqual(tabelas[1]['rotulo_total'], 'produtos')
        self.assertEqual(resposta['metadados']['rotulo_total'], 'inventários analisados')

    def test_erro_controlado_nao_expoe_excecao(self):
        resposta = construir_erro('Não foi possível processar.', codigo='processamento')

        self.assertFalse(resposta['sucesso'])
        self.assertEqual(resposta['tipo'], 'erro')
        self.assertNotIn('traceback', str(resposta).lower())

class ToryInterfaceTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Interface Tory')
        self.usuario = User.objects.create_user('tory_interface')
        Perfil.objects.update_or_create(
            user=self.usuario,
            defaults={'empresa': self.empresa, 'role': Perfil.Role.ADMIN},
        )
        self.client.force_login(self.usuario)
        self.url = reverse('estoque:assistente_operacional')

    @patch('estoque.views.AssistenteOperacionalService.responder')
    def test_endpoint_ajax_expoe_contrato_novo_e_legado(self, responder):
        responder.return_value = {
            'categoria': 'estoque',
            'resposta': 'TOTAL | BASE\n3 | Campinas',
            'contexto': {'intencao': 'equipamentos'},
            'acoes': [],
        }

        response = self.client.post(
            self.url,
            {'pergunta': 'Quantos equipamentos existem?'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['sucesso'])
        self.assertEqual(payload['resposta'], payload['mensagem'])
        self.assertTrue(payload['resposta_id'])
        self.assertEqual(payload['componentes'][0]['tipo'], 'tabela')
        self.assertEqual(
            self.client.session['assistente_operacional_contexto'],
            {'intencao': 'equipamentos'},
        )

    def test_endpoint_ajax_rejeita_pergunta_vazia(self):
        response = self.client.post(
            self.url,
            {'pergunta': '   '},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['sucesso'])
        self.assertEqual(response.json()['erro']['codigo'], 'pergunta_vazia')

    @patch('estoque.views.AssistenteOperacionalService.responder', side_effect=PermissionDenied)
    def test_endpoint_ajax_trata_erro_de_permissao(self, responder):
        response = self.client.post(
            self.url,
            {'pergunta': 'Mostre custos'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['erro']['codigo'], 'permissao')

    def test_limpar_conversa_remove_contexto_da_sessao(self):
        session = self.client.session
        session['assistente_operacional_contexto'] = {'intencao': 'estoque'}
        session.save()

        response = self.client.post(
            self.url,
            {'acao': 'limpar_contexto'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('assistente_operacional_contexto', self.client.session)

    def test_pagina_inclui_modal_amplo_e_modulos_estaticos(self):
        response = self.client.get(self.url)

        self.assertContains(response, 'id="tory-modal"')
        self.assertContains(response, 'id="tory-tab-resultados"')
        self.assertContains(response, 'id="tory-question"')
        self.assertContains(response, 'css/tory.css')
        self.assertContains(response, 'js/tory-renderer.js')


class HistoricoDetalhadoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Auditoria')
        self.base = Base.objects.create(nome='SP AUDITORIA', empresa=self.empresa)
        self.usuario = User.objects.create_user(
            'auditor_historico',
            email='auditor@example.com',
            password='segredo-nao-renderizar',
        )
        Perfil.objects.update_or_create(
            user=self.usuario,
            defaults={'empresa': self.empresa, 'role': Perfil.Role.ADMIN},
        )
        self.produto = Produto.objects.create(
            codigo='PROD-AUDIT-1',
            descricao='Coletor auditável',
            fabricante='Fabricante X',
            modelo='Modelo Y',
            categoria='Coletores',
            especificacoes_tecnicas={'memoria': '8 GB'},
        )
        self.equipamento = Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SERIE-AUDIT-1',
            patrimonio='PATR-AUDIT-1',
            regional=self.base,
            responsavel='Operação',
            custo_aquisicao=Decimal('1234.56'),
            codigo='EQP-AUDIT-1',
        )
        self.historico = Historico.objects.create(
            equipamento=self.equipamento,
            tipo_acao='EDICAO',
            usuario=self.usuario,
            detalhes={'motivo': 'registro-interno', 'campo': 'responsavel'},
        )
        self.client.force_login(self.usuario)

    def test_template_exibe_todos_os_campos_persistidos_relacionados(self):
        response = self.client.get(
            reverse('estoque:historico_detalhes', args=[self.historico.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Registro histórico')
        self.assertContains(response, 'Equipamento — estado atual')
        self.assertContains(response, 'especificacoes_tecnicas')
        self.assertContains(response, 'custo_aquisicao')
        self.assertContains(response, 'registro-interno')
        self.assertContains(response, 'auditor@example.com')
        self.assertNotContains(response, self.usuario.password)


class ToryEquipamentosOperacionaisTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Equipamentos Tory')
        self.base = Base.objects.create(nome='SP EQUIPAMENTOS', empresa=self.empresa)
        self.destino = Base.objects.create(nome='SP DESTINO', empresa=self.empresa)
        self.usuario = User.objects.create_user('tory_equipamentos')
        Perfil.objects.update_or_create(
            user=self.usuario,
            defaults={'empresa': self.empresa, 'role': Perfil.Role.ADMIN},
        )
        self.usuario.refresh_from_db()
        self.produto = Produto.objects.create(
            codigo='NOTE-TORY',
            descricao='Notebook Tory',
            fabricante='Fabricante Tory',
            modelo='Modelo Tory',
            categoria='Notebooks',
        )
        self.administrativo = Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SER-ADM-01',
            patrimonio='PAT-ADM-01',
            regional=self.base,
            status='SICK',
            finalidade=Equipamento.Finalidade.ADMINISTRATIVO,
            codigo='EQP-ADM-01',
        )
        self.operacional = Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SER-OPE-01',
            patrimonio='PAT-OPE-01',
            regional=self.base,
            status='ATIVO',
            finalidade=Equipamento.Finalidade.OPERACIONAL,
            codigo='EQP-OPE-01',
        )
        Sick.objects.create(
            equipamento=self.administrativo,
            categoria='HARDWARE',
            motivo='Falha de placa',
            etapa=Sick.Etapa.EM_MANUTENCAO,
            previsao_retorno=date(2026, 7, 30),
            ativo=True,
        )
        transferencia = Transferencia.objects.create(
            solicitado_por=self.usuario,
            regional_origem=self.base,
            regional_destino=self.destino,
            status='EM_TRANSITO',
            protocolo='TRF-TORY-01',
        )
        TransferenciaItem.objects.create(
            transferencia=transferencia,
            equipamento=self.administrativo,
            status='ENVIADO',
        )
        grupo = GrupoRegional.objects.create(nome='Grupo Equipamentos Tory')
        emprestimo = Emprestimo.objects.create(
            protocolo='EMP-TORY-01',
            grupo=grupo,
            regional_origem=self.base,
            regional_destino=self.destino,
            solicitado_por=self.usuario,
            motivo='Apoio administrativo',
            data_emprestimo=date(2026, 7, 20),
            data_prevista_devolucao=date(2026, 7, 31),
            status='EMPRESTADO',
        )
        ItemEmprestimo.objects.create(
            emprestimo=emprestimo,
            equipamento=self.administrativo,
            status='RECEBIDO',
            quantidade=1,
        )
        cliente = Cliente.objects.create(sigla='TEQ', nome='Cliente Equipamentos Tory')
        inventario = Inventario.objects.create(
            cliente=cliente,
            loja='101',
            base=self.base,
            data_inicio=date(2026, 7, 22),
            criado_por=self.usuario,
            status='EM_ANDAMENTO',
        )
        checklist = ChecklistDiario.objects.create(
            inventario=inventario,
            data_inicio=timezone.now(),
            criado_por=self.usuario,
            responsavel=self.usuario,
            status='EM_EXECUCAO',
        )
        ChecklistEquipamento.objects.create(
            checklist=checklist,
            equipamento=self.administrativo,
            tag_saida='TAG-ADM-01',
            status_retorno='PENDENTE',
        )

    def test_detalhe_inclui_finalidade_e_vinculos_operacionais(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Detalhe o equipamento de patrimônio PAT-ADM-01',
        )

        self.assertEqual(resultado['categoria'], 'estoque')
        self.assertEqual(resultado['contexto']['equipamento_identificador'], 'pat-adm-01')
        self.assertIn('Administrativo', resultado['resposta'])
        self.assertIn('Em manutenção · HARDWARE · retorno 30/07/2026', resultado['resposta'])
        self.assertIn('TRF-TORY-01 · Em trânsito', resultado['resposta'])
        self.assertIn('EMP-TORY-01 · Emprestado', resultado['resposta'])
        self.assertIn('TEQ loja 101', resultado['resposta'])

    def test_resumo_inclui_administrativos_e_operacionais(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Mostre os equipamentos da base SP EQUIPAMENTOS',
        )

        self.assertIn('Administrativo | 1 | 50,00%', resultado['resposta'])
        self.assertIn('Operacional | 1 | 50,00%', resultado['resposta'])
        self.assertIn('PAT-ADM-01', resultado['resposta'])
        self.assertIn('PAT-OPE-01', resultado['resposta'])

    def test_filtro_administrativo_nao_retorna_operacional(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Quais equipamentos administrativos existem?',
        )

        self.assertEqual(resultado['contexto']['finalidade'], 'ADMINISTRATIVO')
        self.assertIn('PAT-ADM-01', resultado['resposta'])
        self.assertNotIn('PAT-OPE-01', resultado['resposta'])

    def test_manutencao_com_etapa_prioriza_equipamentos_sobre_contexto_de_inventario(self):
        self.administrativo.status = 'MANUTENCAO'
        self.administrativo.save(update_fields=['status', 'data_atualizacao'])

        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Quais equipamentos estão em manutenção e em qual etapa estão',
            contexto={
                'intencao': 'inventarios_data_base',
                'base': self.destino.nome,
            },
        )

        self.assertEqual(resultado['contexto']['intencao'], 'equipamentos')
        self.assertEqual(resultado['contexto']['status'], 'MANUTENCAO')
        self.assertIn('PAT-ADM-01', resultado['resposta'])
        self.assertIn('Em manutenção · HARDWARE', resultado['resposta'])
        self.assertNotIn('Resumo de inventários', resultado['resposta'])

    def test_sick_com_etapa_nao_herda_base_de_inventario_anterior(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Quais equipamentos estão no SICK e em qual etapa estão?',
            contexto={
                'intencao': 'inventarios_data_base',
                'base': self.destino.nome,
            },
        )

        self.assertEqual(resultado['contexto']['intencao'], 'equipamentos')
        self.assertEqual(resultado['contexto']['status'], 'SICK')
        self.assertEqual(resultado['contexto']['base'], '')
        self.assertIn('PAT-ADM-01', resultado['resposta'])
        self.assertIn('Em manutenção · HARDWARE', resultado['resposta'])

    def test_contrato_torna_identificadores_do_equipamento_clicaveis(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Detalhe o equipamento de série SER-ADM-01',
        )
        contrato = construir_resposta(resultado)
        tabela = next(
            item for item in contrato['componentes']
            if item['tipo'] == 'tabela' and item['titulo'] == 'Equipamentos encontrados'
            and item['registros'] and 'PATRIMÔNIO' in item['registros'][0]
        )
        acoes = tabela['registros'][0]['_acoes_celulas']

        self.assertEqual(
            acoes['PATRIMÔNIO']['pergunta'],
            'Detalhe o equipamento de patrimônio PAT-ADM-01',
        )
        self.assertEqual(
            acoes['SÉRIE']['pergunta'],
            'Detalhe o equipamento de série SER-ADM-01',
        )

class ToryRankingPorBaseTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Ranking Tory')
        self.base_a = Base.objects.create(nome='BASE ALFA', empresa=self.empresa)
        self.base_b = Base.objects.create(nome='BASE BETA', empresa=self.empresa)
        self.usuario = User.objects.create_user('tory_ranking')
        Perfil.objects.update_or_create(
            user=self.usuario,
            defaults={'empresa': self.empresa, 'role': Perfil.Role.ADMIN},
        )
        self.usuario.refresh_from_db()

        produto = Produto.objects.create(
            codigo='COL-RANK',
            descricao='Coletor Ranking',
            categoria='Coletores',
        )
        for indice, base in enumerate((self.base_a, self.base_a, self.base_a, self.base_b), start=1):
            Equipamento.objects.create(
                produto=produto,
                numero_serie=f'RANK-{indice}',
                patrimonio=f'PAT-RANK-{indice}',
                regional=base,
                status='ATIVO',
                finalidade=Equipamento.Finalidade.OPERACIONAL,
            )

        self.cliente = Cliente.objects.create(sigla='RNK', nome='Cliente Ranking')
        for loja, base in (('1', self.base_a), ('2', self.base_a), ('3', self.base_b)):
            Inventario.objects.create(
                cliente=self.cliente,
                loja=loja,
                base=base,
                data_inicio=date(2026, 7, 27),
                criado_por=self.usuario,
                pessoas=5,
                tipo='T',
            )

        categoria = CategoriaInsumo.objects.create(nome='EXPEDIENTE RANKING')
        self.durex = Insumo.objects.create(
            descricao='Durex',
            categoria=categoria,
            unidade_medida='rolos',
        )
        for base, quantidade in ((self.base_a, 10), (self.base_b, 30)):
            MovimentacaoInsumo.objects.create(
                base=base,
                insumo=self.durex,
                tipo='ENTRADA',
                quantidade=quantidade,
                usuario=self.usuario,
            )

        LoteTag.objects.create(
            base=self.base_a,
            numero_inicial=1,
            numero_final=100,
            valor_unitario=Decimal('0.10'),
            quantidade_disponivel=20,
        )
        LoteTag.objects.create(
            base=self.base_b,
            numero_inicial=101,
            numero_final=300,
            valor_unitario=Decimal('0.10'),
            quantidade_disponivel=80,
        )

    def _assert_ranking(self, pergunta, base_esperada, trecho_percentual):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            pergunta,
            contexto={'intencao': 'equipamentos_categoria', 'base': self.base_b.nome},
        )

        self.assertEqual(resultado['contexto']['intencao'], 'ranking_base')
        self.assertEqual(resultado['contexto']['base'], '')
        self.assertTrue(resultado['contexto']['todas_bases'])
        self.assertIn(base_esperada, resultado['resposta'])
        self.assertIn(trecho_percentual, resultado['resposta'])
        self.assertNotIn('Detalhamento operacional', resultado['resposta'])
        tabela = next(item for item in resultado['componentes'] if item['tipo'] == 'tabela')
        self.assertEqual(tabela['registros'][0]['BASE'], base_esperada)
        self.assertEqual(tabela['rotulo_total'], 'bases comparadas')

    def test_ranking_de_equipamentos_ignora_base_antiga_e_exibe_percentual(self):
        self._assert_ranking(
            'Qual a base possui mais coletores?',
            'BASE ALFA',
            '75,00%',
        )

    def test_ranking_de_inventarios_usa_dados_locais_agrupados(self):
        self._assert_ranking(
            'Qual base possui mais inventários?',
            'BASE ALFA',
            '66,67%',
        )

    def test_ranking_de_pessoas_usa_demanda_dos_inventarios(self):
        self._assert_ranking(
            'Qual base possui maior demanda de pessoas?',
            'BASE ALFA',
            '66,67%',
        )

    def test_ranking_de_insumo_dinamico_usa_saldo_atual(self):
        self._assert_ranking(
            'Qual base possui mais durex?',
            'BASE BETA',
            '75,00%',
        )

    def test_ranking_de_tags_usa_quantidade_disponivel(self):
        self._assert_ranking(
            'Qual base possui mais tags?',
            'BASE BETA',
            '80,00%',
        )

    def test_conceito_desconhecido_pede_esclarecimento(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario,
            'Qual base possui mais um item que não existe?',
        )

        self.assertEqual(resultado['contexto']['intencao'], 'esclarecer_ranking')
        self.assertEqual(resultado['categoria'], 'esclarecimento')
        self.assertIn('não identifiquei com segurança', resultado['resposta'])

class ToryIsolamentoBasesTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nome='Empresa Escopo Tory')
        self.santa_isabel = Base.objects.create(
            nome='SP INT STA ISABEL', empresa=self.empresa
        )
        self.outra_base = Base.objects.create(
            nome='SP INT CPN', empresa=self.empresa
        )
        self.outra_empresa = Empresa.objects.create(nome='Outra Empresa Tory')
        self.base_outra_empresa = Base.objects.create(
            nome='BASE OUTRA EMPRESA', empresa=self.outra_empresa
        )
        self.usuario = User.objects.create_user('tory_santa_isabel')
        perfil, _ = Perfil.objects.update_or_create(
            user=self.usuario,
            defaults={'empresa': self.empresa, 'role': Perfil.Role.GESTOR},
        )
        perfil.regionais.set([self.santa_isabel, self.base_outra_empresa])
        self.usuario.refresh_from_db()

        self.produto = Produto.objects.create(
            codigo='COL-ESCOPO-TORY',
            descricao='Coletor Escopo Tory',
            fabricante='Fabricante Tory',
            modelo='Modelo Tory',
            categoria='Coletores',
        )
        self.equipamento_permitido = Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SER-STA-01',
            patrimonio='PAT-STA-01',
            regional=self.santa_isabel,
            status='ATIVO',
            finalidade=Equipamento.Finalidade.ADMINISTRATIVO,
            codigo='EQP-STA-01',
        )
        Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SER-FORA-01',
            patrimonio='PAT-FORA-01',
            regional=self.outra_base,
            status='ATIVO',
            finalidade=Equipamento.Finalidade.OPERACIONAL,
            codigo='EQP-FORA-01',
        )
        Equipamento.objects.create(
            produto=self.produto,
            numero_serie='SER-EMPRESA-01',
            patrimonio='PAT-EMPRESA-01',
            regional=self.base_outra_empresa,
            status='ATIVO',
            finalidade=Equipamento.Finalidade.OPERACIONAL,
            codigo='EQP-EMPRESA-01',
        )

        self.cliente = Cliente.objects.create(
            sigla='ESC', nome='Cliente Escopo Tory'
        )
        Inventario.objects.create(
            cliente=self.cliente,
            loja='STA-101',
            base=self.santa_isabel,
            data_inicio=timezone.localdate(),
            criado_por=self.usuario,
            status='EM_ANDAMENTO',
        )
        Inventario.objects.create(
            cliente=self.cliente,
            loja='FORA-999',
            base=self.outra_base,
            data_inicio=timezone.localdate(),
            criado_por=self.usuario,
            status='EM_ANDAMENTO',
        )
        Inventario.objects.create(
            cliente=self.cliente,
            loja='EMPRESA-999',
            base=self.base_outra_empresa,
            data_inicio=timezone.localdate(),
            criado_por=self.usuario,
            status='EM_ANDAMENTO',
        )

        transferencia = Transferencia.objects.create(
            solicitado_por=self.usuario,
            regional_origem=self.santa_isabel,
            regional_destino=self.outra_base,
            status='EM_TRANSITO',
            protocolo='TRF-ESCOPO-01',
        )
        TransferenciaItem.objects.create(
            transferencia=transferencia,
            equipamento=self.equipamento_permitido,
            status='ENVIADO',
        )

    def test_equipamentos_ficam_restritos_a_base_e_empresa_autorizadas(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario, 'Mostre todos os equipamentos'
        )

        self.assertIn('PAT-STA-01', resultado['resposta'])
        self.assertNotIn('PAT-FORA-01', resultado['resposta'])
        self.assertNotIn('PAT-EMPRESA-01', resultado['resposta'])

    def test_pesquisa_direta_nao_localiza_equipamento_de_outra_base(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario, 'Detalhe o equipamento de patrimônio PAT-FORA-01'
        )

        self.assertIn('não encontrei esse equipamento no seu escopo', resultado['resposta'])
        self.assertNotIn('SER-FORA-01', resultado['resposta'])

    def test_inventarios_ficam_restritos_a_base_e_empresa_autorizadas(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario, 'Mostre todos os inventários'
        )

        self.assertIn('STA-101', resultado['resposta'])
        self.assertNotIn('FORA-999', resultado['resposta'])
        self.assertNotIn('EMPRESA-999', resultado['resposta'])

    def test_base_proibida_e_negada_sem_substituicao_silenciosa(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario, 'Mostre os equipamentos da base SP INT CPN'
        )

        self.assertEqual(resultado['contexto']['intencao'], 'base_sem_acesso')
        self.assertIn('não está vinculada ao seu usuário', resultado['resposta'])
        self.assertNotIn('PAT-STA-01', resultado['resposta'])

    def test_movimentacao_nao_revela_nome_de_base_fora_do_escopo(self):
        resultado = AssistenteOperacionalService.responder(
            self.usuario, 'Detalhe o equipamento de patrimônio PAT-STA-01'
        )

        self.assertIn('TRF-ESCOPO-01', resultado['resposta'])
        self.assertIn('base não exibida', resultado['resposta'])
        self.assertNotIn('SP INT CPN', resultado['resposta'])
