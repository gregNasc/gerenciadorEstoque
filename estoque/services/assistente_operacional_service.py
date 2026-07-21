import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from math import ceil
from numbers import Number

from django.db.models import Case, Count, DecimalField, Q, Sum, Value, When
from django.utils import timezone
from django.utils.dateparse import parse_date

from estoque.models import Base, Equipamento, GrupoRegional, Historico, Produto, Transferencia
from estoque.security import secure_queryset


@dataclass
class InterpretacaoOperacional:
    pergunta: str
    texto: str
    intencao: str = 'orientacao'
    categoria: str = ''
    base: Base | None = None
    grupo: GrupoRegional | None = None
    uf: str = ''
    base_bloqueada: str = ''
    grupo_bloqueado: str = ''
    uf_bloqueada: str = ''
    opcoes_base: list[str] = field(default_factory=list)
    todas_bases: bool = False
    status: str = ''
    data: object | None = None
    protocolo: str = ''
    cliente: object | None = None
    loja: str = ''
    pessoas_filtro: int | None = None
    periodo_inicio: object | None = None
    periodo_fim: object | None = None
    tipo_inventario: str = ''
    insumo: object | None = None
    planning_action: str = 'list'
    planning_statuses: list[str] = field(default_factory=list)
    planning_location: str = ''
    simulated_sporadic_count: int | None = None
    external_event_id: str = ''
    external_client_id: str = ''
    external_client_name: str = ''
    external_store_id: str = ''
    external_store_name: str = ''
    external_region_id: str = ''
    external_region_name: str = ''
    external_inventory_type_name: str = ''
    external_inventory_type_kind: str = ''

class AssistenteOperacionalService:
    NOME_ASSISTENTE = 'Tory'
    ENTRADAS_INSUMO = {'ENTRADA', 'DEVOLUCAO', 'AJUSTE_ENTRADA'}
    SAIDAS_INSUMO = {'SAIDA', 'PERDA', 'AJUSTE_SAIDA'}

    CATEGORIAS = {
        'coletores': 'Coletores',
        'coletor': 'Coletores',
        'coletora': 'Coletores',
        'coletoras': 'Coletores',
        'impressora': 'Impressoras',
        'impressoras': 'Impressoras',
        'notebook': 'Notebooks',
        'notebooks': 'Notebooks',
        'router': 'Routers',
        'routers': 'Routers',
        'roteador': 'Routers',
        'roteadores': 'Routers',
    }

    BASE_ALIASES = {
        'campinas': 'SP INT CPN',
        'cpn': 'SP INT CPN',
        'santa isabel': 'SP INT STA ISABEL',
        'sta isabel': 'SP INT STA ISABEL',
        'sta isa': 'SP INT STA ISABEL',
        'ribeirao preto': 'SP INT RIBEIRÃO',
        'florianopolis': 'SC FLORIPA',
        'floripa': 'SC FLORIPA',
        'rio de janeiro': 'RIO DE JANEIRO',
    }

    UF_ALIASES = {
        'ac': 'AC', 'acre': 'AC', 'al': 'AL', 'alagoas': 'AL',
        'ap': 'AP', 'amapa': 'AP', 'am': 'AM', 'amazonas': 'AM',
        'ba': 'BA', 'bahia': 'BA', 'ce': 'CE', 'ceara': 'CE',
        'df': 'DF', 'distrito federal': 'DF', 'es': 'ES', 'espirito santo': 'ES',
        'go': 'GO', 'goias': 'GO', 'ma': 'MA', 'maranhao': 'MA',
        'mt': 'MT', 'mato grosso': 'MT', 'ms': 'MS', 'mato grosso do sul': 'MS',
        'mg': 'MG', 'minas gerais': 'MG', 'pa': 'PA', 'para': 'PA',
        'pb': 'PB', 'paraiba': 'PB', 'pr': 'PR', 'parana': 'PR',
        'pe': 'PE', 'pernambuco': 'PE', 'pi': 'PI', 'piaui': 'PI',
        'rj': 'RJ', 'rio de janeiro': 'RJ', 'rn': 'RN', 'rio grande do norte': 'RN',
        'rs': 'RS', 'rio grande do sul': 'RS', 'ro': 'RO', 'rondonia': 'RO',
        'rr': 'RR', 'roraima': 'RR', 'sc': 'SC', 'santa catarina': 'SC',
        'sp': 'SP', 'sao paulo': 'SP', 'se': 'SE', 'sergipe': 'SE',
        'to': 'TO', 'tocantins': 'TO',
    }

    CLIENTE_ALIASES = {
        'assai': 'ASI',
        'assai atacadista': 'ASI',
        'asa': 'ASI',
        'oxxo': 'OXX',
        'oxx': 'OXX',
        'osso': 'OXX',
        'mercado oxxo': 'OXX',
    }

    GRUPO_ALIASES = {
        'oxxo interior': 'OXXO INTERIOR',
        'oxxo sp interior': 'OXXO INTERIOR',
        'oxxo int': 'OXXO INTERIOR',
        'oxxo leste': 'OXXO LESTE',
        'oxxo sp leste': 'OXXO LESTE',
        'oxxo sul': 'OXXO SUL/LITORAL',
        'oxxo sp sul': 'OXXO SUL/LITORAL',
        'oxxo litoral': 'OXXO SUL/LITORAL',
        'oxxo sul litoral': 'OXXO SUL/LITORAL',
    }

    INTENCOES_COM_ESCOPO_DE_BASE = {
        'capacidade_coletores',
        'capacidade_equipamentos',
        'inventarios_data_base',
        'equipamentos_categoria',
        'equipamentos',
        'insumos',
        'inventarios_checklists',
        'indicadores',
        'inventarios_relatorio',
    }

    @classmethod
    def responder(cls, user, pergunta, contexto=None):
        interpretacao = cls.interpretar(user, pergunta, contexto=contexto)

        roteadores = {
            'planejamento': cls._planejamento,
            'capacidade_coletores': cls._capacidade_coletores,
            'capacidade_equipamentos': cls._capacidade_equipamentos,
            'inventarios_data_base': cls._inventarios_data_base,
            'inventarios_relatorio': cls._inventarios_relatorio,
            'custos_insumos': cls._custos_insumos,
            'comparacao_precos': cls._comparacao_precos,
            'solicitacoes_insumos': cls._solicitacoes_insumos,
            'testes_sistema': cls._testes_sistema,
            'equipamentos_categoria': cls._equipamentos_categoria,
            'equipamentos': cls._equipamentos,
            'insumos': cls._insumos,
            'transferencias': cls._transferencias,
            'historico': cls._historico,
            'inventarios_checklists': cls._inventarios_checklists,
            'indicadores': cls._indicadores,
            'escolher_base': cls._escolher_base,
            'base_sem_acesso': cls._base_sem_acesso,
            'grupo_sem_acesso': cls._grupo_sem_acesso,
            'uf_sem_acesso': cls._uf_sem_acesso,
            'saudacao': cls._saudacao,
            'ajuda_sistema': cls._ajuda_sistema,
            'glossario': cls._explicar_termo,
            'orientacao': cls._orientacao,
        }

        resposta = roteadores.get(interpretacao.intencao, cls._orientacao)(user, interpretacao)
        acoes_contextuais = resposta.pop('acoes', [])
        resposta['resposta'] = cls._personalizar_resposta(
            user,
            resposta['resposta'],
            pergunta=pergunta,
            intencao=interpretacao.intencao,
        )
        resposta['interpretacao'] = cls._resumo_interpretacao(interpretacao)
        resposta['contexto'] = cls._contexto_interpretacao(interpretacao)
        resposta['acoes'] = acoes_contextuais or cls._acoes_interpretacao(interpretacao)
        return resposta

    @classmethod
    def interpretar(cls, user, pergunta, contexto=None):
        contexto = contexto or {}
        pergunta = (pergunta or '').strip()
        texto = cls._corrigir_termos(cls._normalizar(pergunta))
        texto = cls._remover_vocativo_tory(texto)
        texto = cls._interpretar_linguagem_cotidiana(texto)
        continuacao = cls._eh_continuacao(texto)
        consulta_relatorio = cls._pergunta_relatorio_inventario(texto)
        consulta_tempo_operacional = cls._pergunta_tempos_operacionais(texto)
        consulta_custo = not consulta_tempo_operacional and (cls._pergunta_custo_insumo(texto) or (
            contexto.get('intencao') == 'custos_insumos' and
            (
                continuacao or
                cls._tem(texto, 'cliente', 'loja', 'base', 'tipo', 'pessoas', 'periodo') or
                re.search(r'\b(hoje|ontem|semana|mes|ano)\b', texto)
            )
        ))
        consulta_detalhe = cls._tem(
            texto, 'previsao', 'pecas', 'produtividade', 'prod media',
            'media', 'endereco', 'cnpj', 'cep', 'bairro', 'cidade',
            'lider', 'qual dia', 'qual data', 'quando', 'pessoas', 'apoio',
            'etapa', 'tipo', 'horario', 'historico', 'duracao', 'durou', 'demorou',
            'comecou', 'terminou', 'atraso', 'tempo efetivo', 'tempo produtivo',
            'depois das', 'antes das', 'acima da media', 'custo adicional',
            'ultrapassou', 'ultrapassar',
        )
        simulacao_equipe_contextual = cls._pergunta_simulacao_equipe(texto)
        cliente_explicito = cls._extrair_cliente(texto)
        cliente = None if cls._quer_todos_clientes(texto) else (
            cliente_explicito or cls._cliente_do_contexto(contexto)
        )
        insumo = cls._extrair_insumo(texto)
        if not insumo and (continuacao or contexto.get('intencao') == 'comparacao_precos'):
            insumo = cls._insumo_do_contexto(contexto)
        loja = cls._extrair_loja(texto, cliente)
        pessoas_filtro = cls._extrair_pessoas_filtro(texto)
        tipo_inventario = cls._extrair_tipo_inventario(texto) or contexto.get('tipo_inventario', '')
        if not loja and (
            simulacao_equipe_contextual or
            (pessoas_filtro is None and (continuacao or consulta_detalhe))
        ):
            loja = contexto.get('loja', '')
        if pessoas_filtro is None and (continuacao or consulta_relatorio):
            pessoas_filtro = contexto.get('pessoas_filtro')
        periodo_inicio_atual, periodo_fim_atual = cls._extrair_periodo(texto)
        periodo_inicio, periodo_fim = periodo_inicio_atual, periodo_fim_atual
        if not periodo_inicio and (
            continuacao or consulta_custo or
            contexto.get('intencao') == 'planejamento' or
            (consulta_relatorio and not cliente_explicito)
        ):
            periodo_inicio = cls._data_contexto_chave(contexto, 'periodo_inicio')
            periodo_fim = cls._data_contexto_chave(contexto, 'periodo_fim')
        data_interpretada_atual = cls._extrair_data(texto)
        data_interpretada = data_interpretada_atual
        if not data_interpretada and periodo_inicio and periodo_inicio == periodo_fim:
            data_interpretada = periodo_inicio
        todas_bases = cls._quer_todas_bases(texto) or (
            continuacao and bool(contexto.get('todas_bases'))
        )
        base_explicita = bool(re.search(r'\b(?:na\s+)?base\s+', texto))
        opcoes_base_ambiguas = (
            [] if todas_bases or base_explicita
            else cls._opcoes_base_para_local_ambiguo(user, texto)
        )
        if base_explicita:
            uf_solicitada = ''
            base_solicitada = cls._extrair_base_global(texto)
        else:
            uf_solicitada = None if todas_bases or opcoes_base_ambiguas else cls._extrair_uf(texto)
            base_solicitada = (
                None if todas_bases or uf_solicitada or opcoes_base_ambiguas
                else cls._extrair_base_global(texto)
            )
        grupo_solicitado = cls._extrair_grupo_global(texto)
        if grupo_solicitado and cls._normalizar(grupo_solicitado.nome).startswith('oxxo '):
            uf_solicitada = ''
        base_visivel = cls._validar_base_visivel(user, base_solicitada) if base_solicitada else None
        if not base_visivel and not todas_bases and not uf_solicitada:
            base_visivel = cls._extrair_base(user, texto)
        grupo_visivel = cls._validar_grupo_visivel(user, grupo_solicitado) if grupo_solicitado else None
        sem_novo_escopo = not (base_solicitada or uf_solicitada or grupo_solicitado or todas_bases)
        if not base_visivel and sem_novo_escopo:
            base_visivel = cls._base_do_contexto(user, contexto)
        if not grupo_visivel and sem_novo_escopo:
            grupo_visivel = cls._grupo_do_contexto(user, contexto)
        uf_contexto = contexto.get('uf', '') if sem_novo_escopo else ''
        uf = uf_solicitada or uf_contexto
        bases_uf = cls._bases_da_uf_visiveis(user, uf) if uf else []
        uf_bloqueada = uf if uf and not bases_uf else ''
        bases_visiveis = cls._bases_visiveis(user)
        if uf and len(bases_visiveis) == 1 and bases_uf == bases_visiveis:
            base_visivel = bases_visiveis[0]
            uf = ''
            uf_bloqueada = ''
        if not base_visivel and not grupo_visivel and not uf and not todas_bases:
            if len(bases_visiveis) == 1:
                base_visivel = bases_visiveis[0]
        categoria = cls._extrair_categoria(texto)
        if contexto.get('intencao') == 'capacidade_coletores' and (todas_bases or grupo_visivel) and not categoria:
            categoria = 'Coletores'
        if todas_bases and not categoria:
            categoria = contexto.get('categoria', '')

        contexto_planejamento = contexto.get('intencao') == 'planejamento'
        planning_action = cls._planning_action(texto, contexto)
        planning_location_atual = cls._extrair_local_planejamento(texto)
        novo_escopo_planejamento = bool(
            data_interpretada_atual or periodo_inicio_atual or base_solicitada or grupo_solicitado or
            uf_solicitada or cliente_explicito or loja or planning_location_atual
        )
        manter_entidades_externas = contexto_planejamento and not novo_escopo_planejamento
        external_event_id = cls._extrair_external_event_id(texto) or (
            contexto.get('external_event_id', '') if manter_entidades_externas else ''
        )
        external_region_id = contexto.get('external_region_id', '') if manter_entidades_externas else ''
        external_client_id = contexto.get('external_client_id', '') if manter_entidades_externas else ''
        external_store_id = contexto.get('external_store_id', '') if manter_entidades_externas else ''
        external_type_name = contexto.get('external_inventory_type_name', '') if manter_entidades_externas else ''
        external_type_kind = (
            cls._extrair_kind_planejamento(texto) or
            (contexto.get('external_inventory_type_kind', '') if manter_entidades_externas else '')
        )
        if planning_action in {'hierarchy', 'highest_pieces', 'highest_headcount'}:
            external_event_id = ''
        if planning_action == 'hierarchy':
            external_type_name = ''
            external_type_kind = ''
        if cls._tem(texto, 'volte ao planejamento', 'mostre os inventarios planejados'):
            external_event_id = ''

        interpretacao = InterpretacaoOperacional(
            pergunta=pergunta,
            texto=texto,
            categoria=categoria,
            base=base_visivel,
            grupo=grupo_visivel,
            uf=uf,
            base_bloqueada=base_solicitada.nome if base_solicitada and not base_visivel else '',
            grupo_bloqueado=grupo_solicitado.nome if grupo_solicitado and not grupo_visivel else '',
            uf_bloqueada=uf_bloqueada,
            todas_bases=todas_bases,
            status='ATIVO' if cls._tem(texto, 'ativo', 'ativos', 'disponivel', 'disponiveis') else contexto.get('status', ''),
            data=data_interpretada,
            protocolo=cls._extrair_protocolo(pergunta),
            cliente=cliente,
            loja=loja,
            pessoas_filtro=pessoas_filtro,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            tipo_inventario=tipo_inventario,
            insumo=insumo,
            planning_action=planning_action,
            planning_statuses=cls._extrair_status_planejamento(texto) or (
                contexto.get('planning_statuses', []) if contexto_planejamento else []
            ),
            planning_location=(
                planning_location_atual or
                (contexto.get('planning_location', '') if manter_entidades_externas else '')
            ),
            simulated_sporadic_count=cls._extrair_avulsos_simulados(texto),
            external_event_id=external_event_id,
            external_client_id=external_client_id,
            external_client_name=contexto.get('external_client_name', '') if manter_entidades_externas else '',
            external_store_id=external_store_id,
            external_store_name=contexto.get('external_store_name', '') if manter_entidades_externas else '',
            external_region_id=external_region_id,
            external_region_name=contexto.get('external_region_name', '') if manter_entidades_externas else '',
            external_inventory_type_name=external_type_name,
            external_inventory_type_kind=external_type_kind,
        )

        if not pergunta:
            return interpretacao

        if opcoes_base_ambiguas:
            interpretacao.intencao = 'escolher_base'
            interpretacao.opcoes_base = [base.nome for base in opcoes_base_ambiguas]
            return interpretacao

        if cls._eh_saudacao(texto):
            # Uma nova saudação inicia um atendimento limpo e remove filtros antigos.
            return InterpretacaoOperacional(
                pergunta=pergunta,
                texto=texto,
                intencao='saudacao',
                base=cls._base_unica_visivel(user),
            )

        if cls._pergunta_sobre_termo(texto):
            interpretacao.intencao = 'glossario'
            return interpretacao

        if cls._pergunta_de_ajuda(texto):
            interpretacao.intencao = 'ajuda_sistema'
            return interpretacao

        if cls._pergunta_planejamento(texto, contexto):
            interpretacao.intencao = 'planejamento'
            # Em planejamento, uma cidade/regional representa o escopo externo. Ela
            # não pode ser convertida silenciosamente em uma base local quando há
            # mais de uma operação no mesmo local (por exemplo, regular e OXXO).
            if planning_location_atual and not base_explicita:
                interpretacao.base = None
                interpretacao.base_bloqueada = ''
        elif cls._pergunta_comparacao_precos(texto) or (
            contexto.get('intencao') == 'comparacao_precos' and continuacao
        ):
            interpretacao.intencao = 'comparacao_precos'
        elif cls._pergunta_solicitacao_insumos(texto) or (
            contexto.get('intencao') == 'solicitacoes_insumos' and
            (continuacao or cls._tem(texto, 'status', 'situacao', 'andamento'))
        ):
            interpretacao.intencao = 'solicitacoes_insumos'
        elif consulta_custo:
            interpretacao.intencao = 'custos_insumos'
        elif cls._pergunta_testes_sistema(texto) or (
            contexto.get('intencao') == 'testes_sistema' and
            (continuacao or re.search(r'\b(semana|mes|hoje|amanha|ontem)\b', texto))
        ):
            interpretacao.intencao = 'testes_sistema'
        elif contexto.get('intencao') == 'inventarios_relatorio' and (
            continuacao or re.search(r'\b(semana|mes|hoje|amanha|ontem)\b', texto)
        ):
            interpretacao.intencao = 'inventarios_relatorio'
        elif consulta_relatorio and (
            interpretacao.cliente or
            interpretacao.loja or
            interpretacao.pessoas_filtro is not None or
            cls._tem(
                texto, 'previsao', 'pecas', 'produtividade', 'prod media', 'media',
                'endereco', 'cnpj', 'cep', 'lider', 'qual dia', 'qual data', 'quando',
                'pessoas', 'apoio', 'etapa', 'tipo', 'horario', 'historico',
                'duracao', 'durou', 'demorou', 'comecou', 'terminou', 'atraso',
                'tempo efetivo', 'tempo produtivo', 'depois das', 'antes das',
                'custo adicional', 'ultrapassou', 'ultrapassar',
            ) or
            (
                interpretacao.periodo_inicio and interpretacao.periodo_fim and
                interpretacao.periodo_inicio != interpretacao.periodo_fim
            )
        ):
            interpretacao.intencao = 'inventarios_relatorio'
        elif cls._pergunta_capacidade_contextual(texto, contexto):
            interpretacao.intencao = 'capacidade_equipamentos'
            interpretacao.data = interpretacao.data or cls._data_contexto(contexto)
        elif (
            interpretacao.cliente and
            not cls._tem(texto, 'equipamento', 'equipamentos', 'insumo', 'insumos') and
            (
                interpretacao.periodo_inicio or
                re.search(r'\b(quantos|quantas|quantidade|total)\b', texto)
            )
        ):
            interpretacao.intencao = 'inventarios_relatorio'
        elif interpretacao.cliente and interpretacao.loja:
            interpretacao.intencao = 'inventarios_relatorio'
        elif cliente_explicito:
            interpretacao.intencao = 'inventarios_relatorio'
        elif (todas_bases or interpretacao.grupo or interpretacao.uf) and contexto.get('intencao') == 'capacidade_coletores':
            interpretacao.intencao = 'capacidade_coletores'
            interpretacao.data = interpretacao.data or cls._data_contexto(contexto)
        elif (todas_bases or interpretacao.grupo or interpretacao.uf) and contexto.get('intencao') == 'capacidade_equipamentos':
            interpretacao.intencao = 'capacidade_equipamentos'
            interpretacao.data = interpretacao.data or cls._data_contexto(contexto)
        elif (
            (todas_bases or interpretacao.grupo or interpretacao.uf) and
            contexto.get('intencao') == 'inventarios_data_base' and
            not interpretacao.categoria and
            not cls._tem(texto, 'equipamento', 'equipamentos', 'insumo', 'insumos')
        ):
            interpretacao.intencao = 'inventarios_data_base'
            interpretacao.data = interpretacao.data or cls._data_contexto(contexto)
        elif todas_bases and interpretacao.categoria:
            interpretacao.intencao = 'equipamentos_categoria'
        elif cls._tem(texto, 'pessoas', 'equipe', 'atende', 'atendida', 'atendido', 'suficiente') and (
            not interpretacao.categoria or
            interpretacao.categoria == 'Coletores' or
            cls._tem(texto, 'coletor', 'coletores')
        ):
            interpretacao.intencao = 'capacidade_coletores'
            interpretacao.categoria = 'Coletores'
            interpretacao.data = interpretacao.data or cls._data_contexto(contexto)
        elif (
            interpretacao.base and
            re.search(r'\b(atende|atendem|atenderia|atendimento)\b', texto) and
            not cls._tem(texto, 'insumo', 'insumos')
        ):
            interpretacao.intencao = 'capacidade_coletores'
            interpretacao.categoria = 'Coletores'
            interpretacao.data = interpretacao.data or cls._data_contexto(contexto)
        elif (
            cls._tem(texto, 'inventario', 'inventarios') and
            cls._tem(texto, 'equipamento', 'equipamentos') and
            re.search(r'\b(atende|atendem|atender|suficiente|tem|temos|possui|possuimos|existe|existem)\b', texto)
        ):
            interpretacao.intencao = 'capacidade_equipamentos'
        elif cls._tem(texto, 'inventario', 'inventarios') and (interpretacao.base or interpretacao.grupo or interpretacao.uf or interpretacao.data):
            interpretacao.intencao = 'inventarios_data_base'
        elif interpretacao.categoria:
            interpretacao.intencao = 'equipamentos_categoria'
        elif cls._tem(texto, 'dashboard', 'indicador', 'indicadores', 'kpi', 'resumo geral', 'geral'):
            interpretacao.intencao = 'indicadores'
        elif cls._tem(texto, 'transferencia', 'transferencias', 'protocolo'):
            interpretacao.intencao = 'transferencias'
        elif cls._tem(texto, 'historico', 'movimentacao', 'movimentacoes', 'acao', 'acoes'):
            interpretacao.intencao = 'historico'
        elif cls._tem(texto, 'insumo', 'insumos', 'tag', 'tags', 'material', 'materiais'):
            interpretacao.intencao = 'insumos'
        elif cls._tem(texto, 'inventario', 'inventarios', 'checklist', 'checklists'):
            interpretacao.intencao = 'inventarios_checklists'
        elif cls._tem(texto, 'estoque', 'equipamento', 'equipamentos', 'patrimonio', 'serie', 'base'):
            interpretacao.intencao = 'equipamentos'

        selecao_base_contextual = bool(
            base_explicita and
            interpretacao.base and
            contexto.get('intencao') in cls.INTENCOES_COM_ESCOPO_DE_BASE and
            re.match(r'^(?:na\s+)?base\s+', texto)
        )
        if selecao_base_contextual:
            interpretacao.intencao = contexto['intencao']
            interpretacao.categoria = interpretacao.categoria or contexto.get('categoria', '')
            interpretacao.data = interpretacao.data or cls._data_contexto(contexto)
            interpretacao.periodo_inicio = (
                interpretacao.periodo_inicio or
                cls._data_contexto_chave(contexto, 'periodo_inicio')
            )
            interpretacao.periodo_fim = (
                interpretacao.periodo_fim or
                cls._data_contexto_chave(contexto, 'periodo_fim')
            )

        if (
            interpretacao.intencao == 'orientacao' and
            (interpretacao.base or interpretacao.grupo or interpretacao.uf or interpretacao.todas_bases) and
            contexto.get('intencao') in cls.INTENCOES_COM_ESCOPO_DE_BASE
        ):
            interpretacao.intencao = contexto['intencao']
            interpretacao.categoria = interpretacao.categoria or contexto.get('categoria', '')
            interpretacao.data = interpretacao.data or cls._data_contexto(contexto)

        cls._aplicar_escopo_de_base(user, interpretacao)
        return interpretacao

    @classmethod
    def _planejamento(cls, user, interpretacao):
        from estoque.services.planning_assistant_service import PlanningAssistantService

        return PlanningAssistantService.respond(user, interpretacao)

    @classmethod
    def _aplicar_escopo_de_base(cls, user, interpretacao):
        if interpretacao.base_bloqueada:
            interpretacao.intencao = 'base_sem_acesso'
            return

        if interpretacao.grupo_bloqueado:
            interpretacao.intencao = 'grupo_sem_acesso'
            return

        if interpretacao.uf_bloqueada:
            interpretacao.intencao = 'uf_sem_acesso'
            return

        if interpretacao.intencao in {'transferencias', 'historico'} and interpretacao.protocolo:
            return

        if interpretacao.todas_bases or interpretacao.grupo or interpretacao.uf:
            return

        if interpretacao.intencao == 'inventarios_relatorio':
            return

        if interpretacao.intencao == 'testes_sistema':
            return

        if interpretacao.intencao == 'custos_insumos':
            return

        if interpretacao.intencao not in cls.INTENCOES_COM_ESCOPO_DE_BASE and interpretacao.intencao not in {'transferencias', 'historico'}:
            return

        if interpretacao.base:
            return

        bases = cls._bases_visiveis(user)
        if len(bases) == 1:
            interpretacao.base = bases[0]
            return

        if len(bases) > 1:
            interpretacao.intencao = 'escolher_base'
            interpretacao.opcoes_base = [base.nome for base in bases]

    @classmethod
    def _capacidade_coletores(cls, user, interpretacao):
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        if interpretacao.grupo or interpretacao.uf or interpretacao.todas_bases:
            return cls._capacidade_coletores_por_bases(user, interpretacao)

        if not interpretacao.base:
            return cls._resposta(
                'capacidade',
                'Para validar se a base atende a quantidade de pessoas, preciso saber qual base vinculada ao seu usuario voce quer consultar.'
            )

        data_ref = interpretacao.data or timezone.localdate()
        inventarios = secure_queryset_insumos(
            Inventario.objects.select_related('base', 'cliente'),
            user,
            campo_base='base',
        ).filter(
            base=interpretacao.base,
            data_inicio=data_ref,
        )

        inventarios_lista = list(inventarios)
        grupos_inventario = cls._agrupar_inventarios_logicos(inventarios_lista)
        pessoas = sum(cls._pessoas_inventario(inv) for inv in inventarios_lista)
        coletores = cls._equipamentos_visiveis(user).filter(
            regional=interpretacao.base,
            produto__categoria__iexact='Coletores',
        )
        coletores_cadastrados = coletores.count()
        coletores_ativos = coletores.filter(
            status='ATIVO',
            finalidade=Equipamento.Finalidade.OPERACIONAL,
        ).count()

        if not inventarios_lista:
            return cls._resposta(
                'capacidade',
                f'nao encontrei inventario para {interpretacao.base.nome} em {data_ref:%d/%m/%Y} no seu escopo. '
                'Sem inventario do dia, nao consigo ler a coluna Pessoas para comparar com os coletores cadastrados.'
            )

        saldo = coletores_ativos - pessoas
        if saldo >= 0:
            situacao = 'ATENDE'
            diferenca = f'Sobram {saldo} coletor(es)'
        else:
            situacao = 'NÃO ATENDE'
            diferenca = f'Faltam {abs(saldo)} coletor(es)'

        titulo = (
            f'Confirmação da capacidade da base {interpretacao.base.nome} em {data_ref:%d/%m/%Y}'
            if cls._eh_confirmacao_capacidade(interpretacao.texto)
            else f'Análise da base {interpretacao.base.nome} em {data_ref:%d/%m/%Y}'
        )
        linhas = [
            titulo,
            '',
            'INVENTÁRIOS | PESSOAS PREVISTAS | COLETORES CADASTRADOS | COLETORES ATIVOS',
            f'{len(grupos_inventario)} | {pessoas} | {coletores_cadastrados} | {coletores_ativos}',
            '',
            'SITUAÇÃO | DIFERENÇA',
            f'{situacao} | {diferenca}',
        ]
        return cls._resposta('capacidade', '\n'.join(linhas))

    @classmethod
    def _capacidade_equipamentos(cls, user, interpretacao):
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        if interpretacao.grupo or interpretacao.uf or interpretacao.todas_bases:
            return cls._capacidade_equipamentos_por_bases(user, interpretacao)

        data_ref = interpretacao.data or timezone.localdate()
        inventarios = list(
            secure_queryset_insumos(
                Inventario.objects.select_related('base', 'cliente'),
                user,
                campo_base='base',
            ).filter(base=interpretacao.base, data_inicio=data_ref)
        )
        grupos_inventario = cls._agrupar_inventarios_logicos(inventarios)
        pessoas = sum(cls._pessoas_inventario(inv) for inv in inventarios)
        equipamentos = cls._equipamentos_visiveis(user).filter(regional=interpretacao.base)
        coletores_ativos = equipamentos.filter(
            produto__categoria__iexact='Coletores',
            status='ATIVO',
            finalidade=Equipamento.Finalidade.OPERACIONAL,
        ).count()
        saldo = coletores_ativos - pessoas
        if not inventarios:
            resultado = 'SEM DEMANDA: não há inventário programado para comparar neste dia.'
        elif saldo >= 0:
            resultado = f'ATENDE: sobram {saldo} coletor(es).'
        else:
            resultado = f'NÃO ATENDE: faltam {abs(saldo)} coletor(es).'

        linhas = [
            f'Análise operacional de {interpretacao.base.nome} em {data_ref:%d/%m/%Y}',
            '',
        ]
        if inventarios:
            linhas.append('INVENTÁRIO | TIPOS | PESSOAS | STATUS')
            for grupo in grupos_inventario:
                inv = grupo['representante']
                linhas.append(
                    f'{inv.cliente.sigla} loja {inv.loja} | {", ".join(grupo["tipos"])} | '
                    f'{grupo["pessoas"]} | {grupo["status"]}'
                )
        else:
            linhas.append('Nenhum inventário programado para esta base na data consultada.')

        linhas.extend([
            '',
            f'Demanda total: {pessoas} pessoa(s)',
            f'Resultado para coletores: {resultado}',
            '',
            'CATEGORIA | PRODUTO | ATIVOS | EM USO | MANUTENÇÃO | TOTAL',
        ])
        produtos = (
            equipamentos.values('produto__categoria', 'produto__descricao')
            .annotate(
                ativos=Count('id', filter=Q(
                    status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
                )),
                em_uso=Count('id', filter=Q(status='EM_USO')),
                manutencao=Count('id', filter=Q(status__in=['MANUTENCAO', 'SICK'])),
                total=Count('id'),
            )
            .order_by('produto__categoria', 'produto__descricao')
        )
        for item in produtos:
            linhas.append(
                f"{item['produto__categoria'] or '-'} | {item['produto__descricao'] or '-'} | "
                f"{item['ativos']} | {item['em_uso']} | {item['manutencao']} | {item['total']}"
            )

        linhas.extend([
            '',
            'Observação: a suficiência é calculada para coletores, usando 1 coletor ativo por pessoa prevista. '
            'As demais categorias são exibidas para conferência, pois ainda não existe uma quantidade mínima configurada para elas.',
        ])
        return cls._resposta('capacidade', '\n'.join(linhas))

    @classmethod
    def _capacidade_equipamentos_por_bases(cls, user, interpretacao):
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        if interpretacao.grupo:
            bases = cls._bases_do_grupo_visiveis(user, interpretacao.grupo)
            escopo = f'grupo regional {interpretacao.grupo.nome}'
        elif interpretacao.uf:
            bases = cls._bases_da_uf_visiveis(user, interpretacao.uf)
            escopo = f'UF {interpretacao.uf}'
        else:
            bases = cls._bases_visiveis(user)
            escopo = 'todas as bases do seu escopo'
        data_ref = interpretacao.data or timezone.localdate()
        inventarios = list(
            secure_queryset_insumos(
                Inventario.objects.select_related('base'),
                user,
                campo_base='base',
            ).filter(base__in=bases, data_inicio=data_ref)
        )
        pessoas_por_base = {}
        inventarios_por_base = {}
        for inv in inventarios:
            pessoas_por_base[inv.base_id] = pessoas_por_base.get(inv.base_id, 0) + cls._pessoas_inventario(inv)
            inventarios_por_base[inv.base_id] = inventarios_por_base.get(inv.base_id, 0) + 1

        equipamentos_por_base = {}
        for item in (
            cls._equipamentos_visiveis(user)
            .filter(
                regional__in=bases, status='ATIVO',
                finalidade=Equipamento.Finalidade.OPERACIONAL,
            )
            .values('regional_id', 'produto__categoria')
            .annotate(total=Count('id'))
        ):
            equipamentos_por_base.setdefault(item['regional_id'], {})[item['produto__categoria']] = item['total']

        atendem = 0
        nao_atendem = 0
        linhas = [
            f'Análise operacional de {escopo} em {data_ref:%d/%m/%Y}',
            '',
            'BASE | INVENTÁRIOS | PESSOAS | COLETORES | IMPRESSORAS | NOTEBOOKS | ROUTERS | RESULTADO',
        ]
        bases_com_demanda = [base for base in bases if inventarios_por_base.get(base.pk, 0)]
        for base in bases_com_demanda:
            por_categoria = equipamentos_por_base.get(base.pk, {})
            pessoas = pessoas_por_base.get(base.pk, 0)
            coletores = por_categoria.get('Coletores', 0)
            if not inventarios_por_base.get(base.pk, 0):
                resultado = 'Sem inventário no dia'
            elif coletores >= pessoas:
                atendem += 1
                resultado = f'Atende, sobram {coletores - pessoas}'
            else:
                nao_atendem += 1
                resultado = f'Não atende, faltam {pessoas - coletores}'
            linhas.append(
                f'{base.nome} | {inventarios_por_base.get(base.pk, 0)} | {pessoas} | {coletores} | '
                f"{por_categoria.get('Impressoras', 0)} | {por_categoria.get('Notebooks', 0)} | "
                f"{por_categoria.get('Routers', 0)} | {resultado}"
            )

        verbo_atendem = 'atende' if atendem == 1 else 'atendem'
        verbo_nao_atendem = 'não atende' if nao_atendem == 1 else 'não atendem'
        linhas.extend([
            '',
            f'Resumo: {len(bases_com_demanda)} base(s) possuem inventários; '
            f'{atendem} {verbo_atendem} e {nao_atendem} {verbo_nao_atendem} à demanda de coletores do dia.',
            'Os números das quatro categorias consideram apenas equipamentos com status ATIVO.',
        ])
        return cls._resposta('capacidade', '\n'.join(linhas))

    @classmethod
    def _inventarios_data_base(cls, user, interpretacao):
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        if interpretacao.grupo:
            return cls._inventarios_por_grupo(user, interpretacao)

        qs = secure_queryset_insumos(
            Inventario.objects.select_related('base', 'cliente'),
            user,
            campo_base='base',
        )

        if interpretacao.base:
            qs = qs.filter(base=interpretacao.base)
        elif interpretacao.uf:
            qs = qs.filter(base__in=cls._bases_da_uf_visiveis(user, interpretacao.uf))
        elif interpretacao.todas_bases:
            qs = qs.filter(base__in=cls._bases_visiveis(user))
        if interpretacao.data:
            qs = qs.filter(data_inicio=interpretacao.data)

        registros = list(qs.order_by('data_inicio', 'cliente__sigla', 'loja', 'base__nome', 'pk'))
        grupos = cls._agrupar_inventarios_logicos(registros)
        total = len(grupos)
        itens = grupos[:10]
        if not grupos:
            partes = []
            if interpretacao.base:
                partes.append(f'base {interpretacao.base.nome}')
            if interpretacao.data:
                partes.append(f'data {interpretacao.data:%d/%m/%Y}')
            filtro = ' para ' + ', '.join(partes) if partes else ''
            return cls._resposta('inventarios', f'Nao encontrei inventarios{filtro} no seu escopo.')

        total_pessoas = sum(grupo['pessoas'] for grupo in grupos)
        titulo_partes = []
        if interpretacao.base:
            titulo_partes.append(f'base {interpretacao.base.nome}')
        elif interpretacao.uf:
            titulo_partes.append(f'UF {interpretacao.uf}')
        elif interpretacao.todas_bases:
            titulo_partes.append('todas as bases do seu escopo')
        if interpretacao.data:
            titulo_partes.append(f'{interpretacao.data:%d/%m/%Y}')
        titulo = ' - '.join(titulo_partes) if titulo_partes else 'seu escopo'

        linhas = [
            f'Resumo de inventarios ({titulo}):',
            '',
            f'- Inventarios encontrados: {total}',
            f'- Pessoas previstas: {total_pessoas}',
            f'- Exibindo: {len(itens)} de {total}',
            '',
            'INVENTÁRIO | TIPOS | PESSOAS | STATUS | BASE | PERÍODO',
        ]
        for grupo in itens:
            inv = grupo['representante']
            linhas.append(
                f'{inv.cliente.sigla} loja {inv.loja} | {", ".join(grupo["tipos"])} | '
                f'{grupo["pessoas"]} | {grupo["status"]} | {inv.base.nome} | '
                f'{cls._formatar_periodo_grupo(grupo)}'
            )
        return cls._resposta('inventarios', '\n'.join(linhas))

    @classmethod
    def _inventarios_relatorio(cls, user, interpretacao):
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        qs = secure_queryset_insumos(
            Inventario.objects.select_related('base', 'cliente'),
            user,
            campo_base='base',
        ).filter(base__in=cls._bases_visiveis(user))

        if interpretacao.base:
            qs = qs.filter(base=interpretacao.base)
        elif interpretacao.uf:
            qs = qs.filter(base__in=cls._bases_da_uf_visiveis(user, interpretacao.uf))
        elif interpretacao.grupo:
            qs = qs.filter(base__in=cls._bases_do_grupo_visiveis(user, interpretacao.grupo))
        if interpretacao.cliente:
            qs = qs.filter(cliente=interpretacao.cliente)
        if interpretacao.loja:
            qs = qs.filter(loja__iexact=interpretacao.loja)
        if (
            interpretacao.pessoas_filtro is not None and
            not cls._pergunta_simulacao_equipe(interpretacao.texto)
        ):
            qs = qs.filter(pessoas=interpretacao.pessoas_filtro)
        if interpretacao.periodo_inicio:
            qs = qs.filter(data_inicio__gte=interpretacao.periodo_inicio)
        if interpretacao.periodo_fim:
            qs = qs.filter(data_inicio__lte=interpretacao.periodo_fim)

        simulacao_equipe = cls._pergunta_simulacao_equipe(interpretacao.texto)
        consulta_tempos = cls._pergunta_tempos_operacionais(interpretacao.texto)
        possui_tempos_reais = simulacao_equipe and qs.filter(
            inicio_real__isnull=False,
            fim_real__isnull=False,
        ).exists()
        if (
            consulta_tempos and
            (not simulacao_equipe or possui_tempos_reais)
        ):
            return cls._tempos_operacionais_inventario(user, interpretacao, qs)

        escopo = cls._descricao_filtro_inventario(interpretacao)
        registros = list(qs.order_by('data_inicio', 'cliente__sigla', 'loja', 'base__nome', 'pk'))
        grupos = cls._agrupar_inventarios_logicos(registros)
        total = len(grupos)
        if not grupos:
            return cls._resposta(
                'inventarios',
                f'não encontrei inventários para {escopo} dentro das bases permitidas ao seu usuário.'
            )

        estimativas = cls._estimar_grupos_inventario(user, grupos)
        if simulacao_equipe and interpretacao.cliente and interpretacao.loja:
            return cls._simular_planejamento_grupo(grupos, estimativas, interpretacao.texto)

        total_pessoas = sum(grupo['pessoas'] for grupo in grupos)
        previsoes_oficiais = [grupo['previsao'] for grupo in grupos if grupo['previsao'] is not None]
        previsoes_estimadas = [
            estimativas[grupo['representante'].pk]['previsao']
            for grupo in grupos
            if grupo['previsao'] is None and estimativas[grupo['representante'].pk]['previsao'] is not None
        ]
        produtividades_oficiais = [grupo['prod_media'] for grupo in grupos if grupo['prod_media'] is not None]
        produtividades_estimadas = [
            estimativas[grupo['representante'].pk]['prod_media']
            for grupo in grupos
            if grupo['prod_media'] is None and estimativas[grupo['representante'].pk]['prod_media'] is not None
        ]
        total_previsao = sum(previsoes_oficiais) + sum(previsoes_estimadas)
        produtividades_completas = produtividades_oficiais + produtividades_estimadas
        media_prod = (
            sum(produtividades_completas) / len(produtividades_completas)
            if produtividades_completas else None
        )
        equipe_contagem_total = sum(
            cls._equipe_produtiva_grupo(grupo)
            for grupo in grupos
            if grupo['previsao'] is not None or estimativas[grupo['representante'].pk]['previsao'] is not None
        )
        carga_media_por_pessoa = (
            total_previsao / equipe_contagem_total
            if equipe_contagem_total and (previsoes_oficiais or previsoes_estimadas)
            else None
        )
        itens = grupos[:10]

        if cls._pergunta_data_inventario(interpretacao.texto):
            linhas = [
                f'Data e etapas do inventário ({escopo})',
                '',
                'CLIENTE | LOJA | PERÍODO | DATA OFICIAL | BASE | TIPOS | PESSOAS',
            ]
            for grupo in itens:
                inv = grupo['representante']
                data_oficial = grupo['pai'].data_inicio if grupo['pai'] else inv.data_inicio
                linhas.append(
                    f'{inv.cliente.sigla} | {inv.loja} | {cls._formatar_periodo_grupo(grupo)} | '
                    f'{data_oficial:%d/%m/%Y} | {inv.base.nome} | {", ".join(grupo["tipos"])} | '
                    f'{grupo["pessoas"]}'
                )
            if total > len(itens):
                linhas.extend(['', f'Exibindo {len(itens)} de {total} inventários. Informe um período para refinar.'])
            linhas.extend(['', 'A data oficial corresponde à etapa T. IM e LO são inventários independentes.'])
            return cls._resposta('inventarios', '\n'.join(linhas))

        if cls._tem(interpretacao.texto, 'lider'):
            linhas = [
                f'Liderança dos inventários ({escopo})',
                '',
                'CLIENTE | LOJA | PERÍODO | BASE | LÍDER | TIPOS',
            ]
            for grupo in itens:
                inv = grupo['representante']
                linhas.append(
                    f'{inv.cliente.sigla} | {inv.loja} | {cls._formatar_periodo_grupo(grupo)} | '
                    f'{inv.base.nome} | {cls._valor_grupo(grupo, "lider")} | {", ".join(grupo["tipos"])}'
                )
            return cls._resposta('inventarios', '\n'.join(linhas))

        if cls._tem(interpretacao.texto, 'endereco', 'cnpj', 'cep', 'bairro', 'cidade'):
            linhas = [
                f'Dados de localização e cadastro ({escopo})',
                '',
                'CLIENTE | LOJA | BASE | DATA | ENDEREÇO | CIDADE | CEP | CNPJ',
            ]
            for grupo in itens:
                inv = grupo['representante']
                endereco = ' - '.join(
                    valor for valor in (
                        cls._valor_grupo(grupo, 'endereco'),
                        cls._valor_grupo(grupo, 'bairro'),
                    ) if valor != '-'
                ) or '-'
                linhas.append(
                    f'{inv.cliente.sigla} | {inv.loja} | {inv.base.nome} | {inv.data_inicio:%d/%m/%Y} | '
                    f'{endereco} | {cls._valor_grupo(grupo, "cidade")} | '
                    f'{cls._valor_grupo(grupo, "cep")} | {cls._valor_grupo(grupo, "cnpj")}'
                )
            if total > len(itens):
                linhas.extend(['', f'Exibindo {len(itens)} de {total} resultados. Informe a loja ou a data para refinar.'])
            return cls._resposta('inventarios', '\n'.join(linhas))

        if cls._tem(interpretacao.texto, 'previsao', 'pecas', 'produtividade', 'prod media', 'producao', 'media'):
            linhas = [
                f'Previsão e produtividade ({escopo})',
                '',
                f'- Inventários encontrados: {total}',
                f'- Alocações pessoa-etapa: {total_pessoas}',
                f'- Equipes de contagem (soma de T + APOIO): {equipe_contagem_total}',
                f'- Previsão total de peças (oficial + estimada): {cls._formatar_numero(total_previsao)}',
                f'- Previsões: {len(previsoes_oficiais)} oficiais, {len(previsoes_estimadas)} estimadas, '
                f'{total - len(previsoes_oficiais) - len(previsoes_estimadas)} sem base comparável',
                f'- Produtividade média: {cls._formatar_decimal(media_prod)} peças por pessoa/hora',
                f'- Produtividades: {len(produtividades_oficiais)} oficiais, '
                f'{len(produtividades_estimadas)} estimadas, '
                f'{total - len(produtividades_oficiais) - len(produtividades_estimadas)} sem base comparável',
                '- Carga prevista por pessoa da equipe de contagem: ' + (
                    f'{cls._formatar_decimal(carga_media_por_pessoa)} peças/pessoa'
                    if carga_media_por_pessoa is not None else 'não calculável com os dados disponíveis'
                ),
                '',
                'CLIENTE | LOJA | PERÍODO | BASE | TIPOS | ALOCAÇÕES | EQUIPE T+APOIO | PREVISÃO PEÇAS | '
                'PROD. PLANEJADA | PEÇAS/PESSOA | DURAÇÃO ESTIMADA',
            ]
            for grupo in itens:
                inv = grupo['representante']
                estimativa = estimativas[inv.pk]
                previsao = grupo['previsao'] if grupo['previsao'] is not None else estimativa['previsao']
                prod_media = grupo['prod_media'] if grupo['prod_media'] is not None else estimativa['prod_media']
                equipe_contagem = cls._equipe_produtiva_grupo(grupo)
                pecas_por_pessoa = (
                    previsao / equipe_contagem
                    if previsao is not None and equipe_contagem
                    else None
                )
                duracao_estimada = cls._duracao_planejada_horas(
                    previsao,
                    equipe_contagem,
                    prod_media,
                )
                previsao_texto = cls._formatar_numero(previsao)
                prod_texto = cls._formatar_decimal(prod_media)
                if grupo['previsao'] is None and previsao is not None:
                    previsao_texto += f' (estimada, n={estimativa["previsao_amostras"]})'
                if grupo['prod_media'] is None and prod_media is not None:
                    prod_texto += f' (estimada, n={estimativa["prod_amostras"]})'
                linhas.append(
                    f'{inv.cliente.sigla} | {inv.loja} | {cls._formatar_periodo_grupo(grupo)} | {inv.base.nome} | '
                    f'{", ".join(grupo["tipos"])} | {grupo["pessoas"]} | {equipe_contagem} | '
                    f'{previsao_texto} | {prod_texto} | '
                    f'{cls._formatar_decimal(pecas_por_pessoa)} | {cls._formatar_horas(duracao_estimada)}'
                )
            linhas.extend([
                '',
                'Nota: “ALOCAÇÕES” soma pessoas de todas as etapas e dias; não representa o tamanho da equipe '
                'produtiva. Para duração e carga por pessoa, Tory usa a equipe T + APOIO. “PROD. PLANEJADA” '
                'é tratada como peças por pessoa/hora, e a duração é PREVISÃO ÷ EQUIPE ÷ PRODUTIVIDADE. '
                'A produtividade real exige peças realizadas, início real e fim real. '
                'Estimativas usam, nesta ordem, médias da mesma loja/cliente, do mesmo cliente com igual número de pessoas '
                'e do cliente em geral.',
            ])
            return cls._resposta('inventarios', '\n'.join(linhas))

        if interpretacao.cliente and interpretacao.loja:
            return cls._detalhar_ciclos_inventario(grupos, escopo)

        linhas = [
            f'Resumo de inventários ({escopo})',
            '',
            f'- Inventários encontrados: {total}',
            f'- Pessoas previstas: {total_pessoas}',
            f'- Exibindo: {len(itens)} de {total}',
            '',
            'CLIENTE | LOJA | PERÍODO | BASE | TIPOS | PESSOAS | STATUS',
        ]
        for grupo in itens:
            inv = grupo['representante']
            linhas.append(
                f'{inv.cliente.sigla} | {inv.loja} | {cls._formatar_periodo_grupo(grupo)} | '
                f'{inv.base.nome} | {", ".join(grupo["tipos"])} | {grupo["pessoas"]} | {grupo["status"]}'
            )
        return cls._resposta('inventarios', '\n'.join(linhas))

    @classmethod
    def _detalhar_ciclos_inventario(cls, grupos, escopo):
        linhas = [f'Detalhamento operacional ({escopo})']
        ordem_tipos = ('PRE', 'CA', 'CP', 'T', 'APOIO', 'D', 'R', 'RC')
        for indice, grupo in enumerate(grupos[:10], start=1):
            inv = grupo['representante']
            status_cliente = (
                getattr(inv.cliente, 'status_relatorio', '') or
                ('ATIVO' if inv.cliente.ativo else 'INATIVO')
            )
            linhas.extend([
                '',
                f'Ciclo {indice}: {inv.cliente.sigla} loja {inv.loja}',
                f'- Período operacional: {cls._formatar_periodo_grupo(grupo)}',
                f'- Data oficial (T): {(grupo["pai"] or inv).data_inicio:%d/%m/%Y}',
                f'- Base responsável: {(grupo["pai"] or inv).base.nome}',
                f'- Status do cliente no relatório: {status_cliente or "INATIVO"}',
                f'- Total de alocações pessoa-etapa: {grupo["pessoas"]}',
                f'- Equipe oficial ampliada (T + APOIO): {grupo["pessoas_oficial_apoio"]}',
                '',
                'ETAPA | PESSOAS',
            ])
            tipos_exibidos = set()
            for tipo in ordem_tipos:
                if tipo in grupo['pessoas_por_tipo']:
                    linhas.append(f'{tipo} | {grupo["pessoas_por_tipo"][tipo]}')
                    tipos_exibidos.add(tipo)
            for tipo, pessoas in grupo['pessoas_por_tipo'].items():
                if tipo not in tipos_exibidos:
                    linhas.append(f'{tipo} | {pessoas}')

            linhas.extend(['', 'DATA | ETAPA | BASE | PESSOAS | ENCONTRO | INÍCIO | LÍDER'])
            for item in sorted(grupo['itens'], key=lambda registro: (registro.data_inicio, registro.pk)):
                linhas.append(
                    f'{item.data_inicio:%d/%m/%Y} | {item.tipo or "-"} | {item.base.nome} | '
                    f'{cls._pessoas_inventario(item)} | {cls._formatar_horario(item.horario_ponto)} | '
                    f'{cls._formatar_horario(item.horario_inicio)} | {item.lider or "-"}'
                )

            pai = grupo['pai']
            if pai:
                historico_data = f'{pai.historico_data:%d/%m/%Y}' if pai.historico_data else '-'
                linhas.extend([
                    '',
                    'HISTÓRICO DE REFERÊNCIA',
                    'EQUIPE | PEÇAS | SATISFAÇÃO | PREPARAÇÃO | LÍDER | DATA',
                    f'{pai.historico_equipe or "-"} | {pai.historico_pecas or "-"} | '
                    f'{pai.historico_satisfacao or "-"} | {cls._formatar_percentual(pai.historico_preparacao)} | '
                    f'{pai.historico_lider or "-"} | {historico_data}',
                ])
            if any(item.horario_inicio and item.horario_inicio.hour >= 18 for item in grupo['itens']):
                linhas.extend([
                    '',
                    'Observação: há etapas com início noturno. O relatório não possui horário de término; '
                    'por isso Tory não presume automaticamente o encerramento na manhã seguinte.',
                ])
        if len(grupos) > 10:
            linhas.extend(['', f'Exibindo 10 de {len(grupos)} ciclos. Informe um período para refinar.'])
        linhas.extend([
            '',
            '“Alocações pessoa-etapa” soma as pessoas de cada etapa e dia; não representa pessoas únicas.',
        ])
        return cls._resposta('inventarios', '\n'.join(linhas))

    @classmethod
    def _tempos_operacionais_inventario(cls, user, interpretacao, qs):
        registros = list(qs.order_by('-data_inicio', '-pk'))
        escopo = cls._descricao_filtro_inventario(interpretacao)
        texto = interpretacao.texto

        if cls._pergunta_ranking_atrasos(texto):
            return cls._ranking_atrasos_por_base(registros, escopo)

        horario_limite = cls._extrair_horario_depois(texto)
        if horario_limite is not None:
            encerrados_depois = [
                inventario for inventario in registros
                if inventario.fim_real and
                cls._datetime_local(inventario.fim_real).time().replace(tzinfo=None) > horario_limite
            ]
            if not encerrados_depois:
                return cls._resposta(
                    'inventarios',
                    f'não encontrei inventários encerrados depois das {horario_limite:%H:%M} para {escopo}. '
                    'A comparação usa o horário real registrado; Tory não presume uma janela fixa.'
                )
            linhas = [
                f'Inventários encerrados depois das {horario_limite:%H:%M} ({escopo})',
                '',
                'CLIENTE | LOJA | BASE | INÍCIO REAL | FIM REAL | DURAÇÃO',
            ]
            for inventario in encerrados_depois[:20]:
                linhas.append(
                    f'{inventario.cliente.sigla} | {inventario.loja} | {inventario.base.nome} | '
                    f'{cls._formatar_datetime(inventario.inicio_real)} | '
                    f'{cls._formatar_datetime(inventario.fim_real)} | '
                    f'{cls._formatar_horas(inventario.duracao_total_horas)}'
                )
            linhas.extend([
                '',
                'O filtro é literal pelo horário de encerramento informado. Inventários diurnos e noturnos '
                'não recebem janelas presumidas.',
            ])
            return cls._resposta('inventarios', '\n'.join(linhas))

        if not registros:
            return cls._resposta(
                'inventarios',
                f'não encontrei inventários para {escopo} dentro das bases permitidas ao seu usuário.'
            )

        inventario = next(
            (
                item for item in registros
                if item.inicio_real or item.fim_real or item.inicio_previsto or item.fim_previsto
            ),
            registros[0],
        )

        if cls._pergunta_simulacao_equipe(texto):
            return cls._simular_equipe_inventario(inventario, texto)

        inicio_hipotetico = cls._extrair_horario_inicio_hipotetico(texto)
        if inicio_hipotetico is not None:
            return cls._simular_inicio_inventario(inventario, inicio_hipotetico)

        horario_alvo = cls._extrair_horario_antes(texto)
        if horario_alvo is not None and cls._tem(texto, 'quantas pessoas', 'quantos profissionais', 'equipe necessaria'):
            return cls._calcular_equipe_para_horario(inventario, horario_alvo)

        return cls._detalhar_tempos_inventario(user, inventario, texto)

    @classmethod
    def _detalhar_tempos_inventario(cls, user, inventario, texto):
        linhas = [f'Inventário {inventario.cliente.sigla} loja {inventario.loja}']
        linhas.extend([
            f'- Início previsto: {cls._formatar_datetime(inventario.inicio_previsto)}',
            f'- Início real: {cls._formatar_datetime(inventario.inicio_real)}',
            f'- Fim previsto: {cls._formatar_datetime(inventario.fim_previsto)}',
            f'- Fim real: {cls._formatar_datetime(inventario.fim_real)}',
            f'- Duração total: {cls._formatar_horas(inventario.duracao_total_horas)}',
            f'- Tempo efetivo de contagem: {cls._formatar_horas(inventario.duracao_contagem_horas)}',
            f'- Tempo fora da contagem: {cls._formatar_horas(inventario.tempo_improdutivo_horas)}',
        ])

        if inventario.atraso_inicio_minutos is None:
            linhas.append('- Cumprimento do início previsto: não calculável sem início previsto e início real')
        elif inventario.atraso_inicio_minutos > 0:
            linhas.append(
                f'- Cumprimento do início previsto: começou com '
                f'{cls._formatar_minutos(inventario.atraso_inicio_minutos)} de atraso'
            )
        elif inventario.atraso_inicio_minutos < 0:
            linhas.append(
                f'- Cumprimento do início previsto: começou '
                f'{cls._formatar_minutos(abs(inventario.atraso_inicio_minutos))} antes'
            )
        else:
            linhas.append('- Cumprimento do início previsto: começou no horário')

        if inventario.desvio_fim_minutos is None:
            linhas.append('- Cumprimento do fim previsto: não calculável sem fim previsto e fim real')
        elif inventario.desvio_fim_minutos > 0:
            linhas.append(
                f'- Cumprimento do fim previsto: encerrou '
                f'{cls._formatar_minutos(inventario.desvio_fim_minutos)} depois'
            )
        elif inventario.desvio_fim_minutos < 0:
            linhas.append(
                f'- Cumprimento do fim previsto: encerrou '
                f'{cls._formatar_minutos(abs(inventario.desvio_fim_minutos))} antes'
            )
        else:
            linhas.append('- Cumprimento do fim previsto: encerrou no horário')

        linhas.extend([
            f'- Peças contadas: {cls._formatar_numero(inventario.total_pecas)}',
            f'- Equipe: {inventario.pessoas if inventario.pessoas is not None else "-"}',
            f'- Peças por pessoa: {cls._formatar_decimal(inventario.pecas_por_pessoa)}',
            '- Produtividade pela duração total: ' + (
                f'{cls._formatar_decimal(inventario.produtividade_pessoa_hora)} peças por pessoa/hora'
                if inventario.produtividade_pessoa_hora is not None else 'não calculável com os dados disponíveis'
            ),
            '- Produtividade no tempo de contagem: ' + (
                f'{cls._formatar_decimal(inventario.produtividade_contagem_pessoa_hora)} peças por pessoa/hora'
                if inventario.produtividade_contagem_pessoa_hora is not None else 'não calculável com os dados disponíveis'
            ),
        ])

        if cls._tem(texto, 'custo', 'custou', 'adicional'):
            if inventario.custo_adicional_atraso is None:
                linhas.append(
                    '- Custo adicional: não calculável sem atraso de encerramento, equipe e custo por pessoa/hora.'
                )
            else:
                linhas.append(
                    f'- Custo adicional pelo encerramento após o previsto: '
                    f'R$ {cls._formatar_decimal(inventario.custo_adicional_atraso)}'
                )

        comparacao = cls._comparar_com_historico(user, inventario)
        if comparacao:
            linhas.extend(['', comparacao])

        if not inventario.inicio_real or not inventario.fim_real:
            linhas.extend([
                '',
                'Os timestamps reais estão incompletos. Tory não usa 20h–6h nem qualquer outra jornada fixa '
                'como substituição.',
            ])
        return cls._resposta('inventarios', '\n'.join(linhas))

    @classmethod
    def _comparar_com_historico(cls, user, inventario):
        if not inventario.inicio_real:
            return ''
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        anteriores = secure_queryset_insumos(
            Inventario.objects.filter(
                cliente=inventario.cliente,
                loja__iexact=inventario.loja,
                inicio_real__lt=inventario.inicio_real,
                fim_real__isnull=False,
            ).select_related('base', 'cliente'),
            user,
            campo_base='base',
        ).order_by('-inicio_real')[:5]
        anteriores = list(anteriores)
        duracoes = [item.duracao_total_horas for item in anteriores if item.duracao_total_horas is not None]
        produtividades = [
            item.produtividade_pessoa_hora
            for item in anteriores
            if item.produtividade_pessoa_hora is not None
        ]
        partes = []
        if duracoes and inventario.duracao_total_horas is not None:
            media = sum(duracoes) / len(duracoes)
            diferenca = inventario.duracao_total_horas - media
            direcao = 'acima' if diferenca >= 0 else 'abaixo'
            partes.append(
                f'A duração ficou {cls._formatar_horas(abs(diferenca))} {direcao} da média dos '
                f'{len(duracoes)} inventários anteriores da mesma loja ({cls._formatar_horas(media)}).'
            )
        if produtividades and inventario.produtividade_pessoa_hora is not None:
            media = sum(produtividades) / len(produtividades)
            variacao = ((inventario.produtividade_pessoa_hora / media) - 1) * 100 if media else 0
            direcao = 'acima' if variacao >= 0 else 'abaixo'
            partes.append(
                f'A produtividade ficou {abs(variacao):.0f}% {direcao} da média histórica comparável.'
            )
        return ' '.join(partes)

    @classmethod
    def _simular_equipe_inventario(cls, inventario, texto):
        if not inventario.pessoas or not inventario.duracao_total_horas or not inventario.inicio_real:
            return cls._resposta(
                'inventarios',
                'não consigo simular a equipe sem quantidade de pessoas, início real e fim real registrados.'
            )
        nova_equipe = cls._extrair_total_equipe_simulada(texto)
        adicional = cls._extrair_adicional_equipe(texto)
        if nova_equipe is None and adicional is not None:
            nova_equipe = inventario.pessoas + adicional
        if not nova_equipe or nova_equipe <= 0:
            return cls._resposta('inventarios', 'informe quantas pessoas terá a equipe simulada.')

        horas_estimadas = inventario.duracao_total_horas * inventario.pessoas / nova_equipe
        termino = inventario.inicio_real + timedelta(hours=horas_estimadas)
        linhas = [
            f'Com {nova_equipe} pessoas, a duração estimada seria {cls._formatar_horas(horas_estimadas)}, '
            f'com término em {cls._formatar_datetime(termino)}.',
            '',
            'A projeção mantém a produtividade individual observada e é linear. Ela não considera perda de '
            'eficiência, espaço físico, curva de aprendizado ou coordenação adicional causada pela mudança da equipe.',
        ]
        return cls._resposta('inventarios', '\n'.join(linhas))

    @classmethod
    def _simular_planejamento_grupo(cls, grupos, estimativas, texto):
        grupo = max(
            grupos,
            key=lambda item: (item['data_inicio'], item['representante'].pk),
        )
        inventario = grupo['representante']
        estimativa = estimativas[inventario.pk]
        previsao = grupo['previsao'] if grupo['previsao'] is not None else estimativa['previsao']
        produtividade = (
            grupo['prod_media']
            if grupo['prod_media'] is not None
            else estimativa['prod_media']
        )
        equipe_atual = cls._equipe_produtiva_grupo(grupo)
        nova_equipe = cls._extrair_total_equipe_simulada(texto)
        adicional = cls._extrair_adicional_equipe(texto)
        if nova_equipe is None and adicional is not None:
            nova_equipe = equipe_atual + adicional

        if not nova_equipe or nova_equipe <= 0:
            return cls._resposta('inventarios', 'informe quantas pessoas terá a equipe simulada.')
        if not previsao or not produtividade:
            return cls._resposta(
                'inventarios',
                'não consigo simular esse planejamento sem previsão de peças e produtividade.'
            )

        duracao_atual = cls._duracao_planejada_horas(previsao, equipe_atual, produtividade)
        duracao_simulada = cls._duracao_planejada_horas(previsao, nova_equipe, produtividade)
        inicio = cls._inicio_planejado_grupo(grupo)
        termino_atual = inicio + timedelta(hours=duracao_atual) if inicio and duracao_atual is not None else None
        termino = inicio + timedelta(hours=duracao_simulada) if inicio and duracao_simulada is not None else None
        origem_produtividade = 'informada no planejamento' if grupo['prod_media'] is not None else 'estimada pelo histórico'
        inicio_texto = cls._formatar_datetime(inicio) if inicio else '-'
        termino_atual_texto = cls._formatar_datetime(termino_atual) if termino_atual else '-'
        termino_simulado_texto = cls._formatar_datetime(termino) if termino else '-'
        linhas = [
            f'Simulação de equipe para {inventario.cliente.sigla} loja {inventario.loja}',
            '',
            'CENÁRIO | EQUIPE | PREVISÃO DE PEÇAS | PRODUTIVIDADE | DURAÇÃO | INÍCIO | TÉRMINO',
            f'Atual | {equipe_atual} | {cls._formatar_numero(previsao)} | '
            f'{cls._formatar_decimal(produtividade)} peças/pessoa/h | {cls._formatar_horas(duracao_atual)} | '
            f'{inicio_texto} | {termino_atual_texto}',
            f'Simulada | {nova_equipe} | {cls._formatar_numero(previsao)} | '
            f'{cls._formatar_decimal(produtividade)} peças/pessoa/h | {cls._formatar_horas(duracao_simulada)} | '
            f'{inicio_texto} | {termino_simulado_texto}',
            '',
            f'Produtividade {origem_produtividade}.',
        ]
        linhas.extend([
            'Fórmula: duração = previsão de peças ÷ equipe de contagem ÷ produtividade.',
            'A projeção é linear e não considera perda de eficiência, limitações físicas ou coordenação adicional '
            'ao aumentar a equipe. A produtividade real só pode ser calculada com peças realizadas e timestamps reais.',
        ])
        return cls._resposta('inventarios', '\n'.join(linhas))

    @staticmethod
    def _equipe_produtiva_grupo(grupo):
        equipe_oficial = grupo['pessoas_oficial_apoio']
        if equipe_oficial:
            return equipe_oficial
        return grupo['pessoas']

    @staticmethod
    def _duracao_planejada_horas(previsao, equipe, produtividade):
        if not previsao or not equipe or not produtividade:
            return None
        return previsao / equipe / produtividade

    @classmethod
    def _inicio_planejado_grupo(cls, grupo):
        inventario = grupo['pai'] or grupo['representante']
        if inventario.inicio_previsto:
            return inventario.inicio_previsto
        if inventario.horario_inicio:
            inicio = datetime.combine(inventario.data_inicio, inventario.horario_inicio)
            return timezone.make_aware(inicio)
        return None

    @classmethod
    def _simular_inicio_inventario(cls, inventario, horario_inicio):
        if not inventario.duracao_total_horas:
            return cls._resposta(
                'inventarios',
                'não consigo projetar o término sem início real e fim real para obter a duração observada.'
            )
        referencia = cls._datetime_local(inventario.inicio_real) if inventario.inicio_real else None
        data_referencia = referencia.date() if referencia else inventario.data_inicio
        inicio = timezone.make_aware(datetime.combine(data_referencia, horario_inicio))
        termino = inicio + timedelta(hours=inventario.duracao_total_horas)
        return cls._resposta(
            'inventarios',
            f'Se tivesse começado em {cls._formatar_datetime(inicio)}, mantendo a duração observada de '
            f'{cls._formatar_horas(inventario.duracao_total_horas)}, terminaria em '
            f'{cls._formatar_datetime(termino)}.'
        )

    @classmethod
    def _calcular_equipe_para_horario(cls, inventario, horario_alvo):
        if not inventario.pessoas or not inventario.duracao_total_horas or not inventario.inicio_real:
            return cls._resposta(
                'inventarios',
                'não consigo dimensionar a equipe sem quantidade de pessoas, início real e fim real registrados.'
            )
        inicio = cls._datetime_local(inventario.inicio_real)
        alvo = timezone.make_aware(datetime.combine(inicio.date(), horario_alvo))
        if alvo <= inicio:
            alvo += timedelta(days=1)
        horas_disponiveis = (alvo - inicio).total_seconds() / 3600
        pessoas = ceil(inventario.pessoas * inventario.duracao_total_horas / horas_disponiveis)
        return cls._resposta(
            'inventarios',
            f'Para concluir até {cls._formatar_datetime(alvo)}, seriam necessárias aproximadamente '
            f'{pessoas} pessoas, mantendo a produtividade individual observada. A projeção é linear e não '
            'considera perdas de eficiência ao ampliar a equipe.'
        )

    @classmethod
    def _ranking_atrasos_por_base(cls, registros, escopo):
        por_base = defaultdict(list)
        for inventario in registros:
            if inventario.atraso_inicio_minutos is not None and inventario.atraso_inicio_minutos > 0:
                por_base[inventario.base.nome].append(inventario.atraso_inicio_minutos)
        if not por_base:
            return cls._resposta(
                'inventarios',
                f'não há atrasos de início calculáveis para {escopo}. São necessários início previsto e início real.'
            )
        ranking = sorted(
            (
                (sum(atrasos) / len(atrasos), len(atrasos), base)
                for base, atrasos in por_base.items()
            ),
            reverse=True,
        )
        linhas = [
            f'Bases com maiores atrasos médios de início ({escopo})',
            '',
            'BASE | ATRASO MÉDIO | INVENTÁRIOS ATRASADOS',
        ]
        for media, quantidade, base in ranking[:10]:
            linhas.append(f'{base} | {cls._formatar_minutos(media)} | {quantidade}')
        linhas.extend(['', 'O ranking considera somente registros com início previsto e início real.'])
        return cls._resposta('inventarios', '\n'.join(linhas))

    @classmethod
    def _custos_insumos(cls, user, interpretacao):
        from insumos.models import Insumo
        from insumos.services.custo_service import CustoInsumoService

        if not CustoInsumoService.pode_visualizar(user):
            return cls._resposta(
                'permissao',
                'essa consulta financeira não está disponível para o seu perfil de acesso.'
            )

        hoje = timezone.localdate()
        inicio = interpretacao.periodo_inicio or hoje.replace(day=1)
        fim = interpretacao.periodo_fim or hoje
        tem_escopo_geografico = bool(
            interpretacao.base or interpretacao.grupo or
            interpretacao.uf or interpretacao.todas_bases
        )
        bases = cls._bases_do_escopo(user, interpretacao) if tem_escopo_geografico else None
        qs = CustoInsumoService.filtrar(
            user,
            inicio=inicio,
            fim=fim,
            cliente=interpretacao.cliente,
            loja=interpretacao.loja,
            tipo=interpretacao.tipo_inventario,
            pessoas=interpretacao.pessoas_filtro,
            bases=bases,
        )
        resumo = CustoInsumoService.resumo(qs)
        consumos = qs.count()
        consumos_sem_custo = qs.filter(valor_unitario__lte=0).count()
        insumos_ativos = Insumo.objects.filter(ativo=True).count()
        insumos_com_preco = Insumo.objects.filter(ativo=True, valor_medio__gt=0).count()

        filtros = [f'{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}']
        if interpretacao.cliente:
            filtros.append(f'cliente {interpretacao.cliente.sigla}')
        if interpretacao.loja:
            filtros.append(f'loja {interpretacao.loja}')
        if interpretacao.tipo_inventario:
            filtros.append(f'tipo {interpretacao.tipo_inventario}')
        if interpretacao.pessoas_filtro is not None:
            filtros.append(f'{interpretacao.pessoas_filtro} pessoas')
        if tem_escopo_geografico:
            filtros.append(cls._descricao_escopo_geografico(interpretacao))
        titulo = 'Gastos com insumos (' + ', '.join(filter(None, filtros)) + ')'

        if not consumos:
            return cls._resposta(
                'custos',
                f'{titulo}\n\nNão encontrei consumos de insumos para esses filtros.'
            )

        linhas = [
            titulo,
            '',
            f'- Gasto registrado: R$ {cls._formatar_decimal(resumo["total"])}',
            f'- Inventários com consumo: {resumo["inventarios"]}',
            f'- Pessoas previstas: {resumo["pessoas"]}',
            f'- Quantidade consumida: {cls._formatar_decimal(resumo["quantidade"])}',
            f'- Custo médio por inventário: R$ {cls._formatar_decimal(resumo["custo_medio_inventario"])}',
            f'- Custo médio por pessoa: R$ {cls._formatar_decimal(resumo["custo_medio_pessoa"])}',
        ]
        if consumos_sem_custo:
            linhas.extend([
                '',
                'ATENÇÃO: o total ainda não é financeiramente confiável.',
                f'- Consumos sem custo unitário: {consumos_sem_custo} de {consumos}',
                f'- Insumos ativos com preço atual: {insumos_com_preco} de {insumos_ativos}',
                '- Valores ausentes são tratados como R$ 0,00 e não são estimados pela Tory.',
            ])

        analise = cls._analisar_ranking_custos(interpretacao.texto)
        dimensao = analise['dimensao']
        maiores = analise['maiores']
        limite = analise['limite']
        acoes = []
        if dimensao == 'base':
            detalhes_bases = CustoInsumoService.por_base(
                qs,
                limite=limite,
                maiores=maiores,
            )
            linhas.extend([
                '',
                'BASE | INVENTÁRIOS | CUSTO TOTAL | CUSTO MÉDIO/INVENTÁRIO | %',
            ])
            if detalhes_bases:
                destaque = detalhes_bases[0]
                linhas.extend([
                    f'Destaque: {destaque["inventario__base__nome"]} — '
                    f'R$ {cls._formatar_decimal(destaque["total"])}.',
                    '',
                ])
            for item in detalhes_bases:
                participacao = (
                    item['total'] * 100 / resumo['total']
                    if resumo['total'] else Decimal('0')
                )
                linhas.append(
                    f'{item["inventario__base__nome"]} | {item["inventarios"]} | '
                    f'R$ {cls._formatar_decimal(item["total"])} | '
                    f'R$ {cls._formatar_decimal(item["custo_medio_inventario"])} | '
                    f'{cls._formatar_decimal(participacao)}%'
                )
            linhas.extend([
                '',
                f'Ranking das {len(detalhes_bases)} bases com '
                f'{"maior" if maiores else "menor"} custo no período, '
                'somando os consumos dos inventários de cada base.',
            ])
            acoes = [
                {'label': 'Ver por cliente', 'pergunta': 'E os maiores custos por cliente?'},
                {'label': 'Ver inventários', 'pergunta': 'Quais inventários tiveram os maiores custos?'},
            ]
        elif dimensao == 'cliente':
            detalhes_clientes = CustoInsumoService.por_cliente(
                qs,
                limite=limite,
                maiores=maiores,
            )
            linhas.extend([
                '',
                'CLIENTE | INVENTÁRIOS | CUSTO TOTAL | %',
            ])
            if detalhes_clientes:
                destaque = detalhes_clientes[0]
                linhas.extend([
                    f'Destaque: {destaque["inventario__cliente__sigla"]} — '
                    f'R$ {cls._formatar_decimal(destaque["total"])}.',
                    '',
                ])
            for item in detalhes_clientes:
                participacao = (
                    item['total'] * 100 / resumo['total']
                    if resumo['total'] else Decimal('0')
                )
                linhas.append(
                    f'{item["inventario__cliente__sigla"]} | {item["inventarios"]} | '
                    f'R$ {cls._formatar_decimal(item["total"])} | {cls._formatar_decimal(participacao)}%'
                )
            linhas.extend([
                '',
                f'Ranking dos {len(detalhes_clientes)} clientes com consumo no período, '
                f'do {"maior" if maiores else "menor"} custo em diante.',
            ])
            acoes = [
                {'label': 'Ver por base', 'pergunta': 'E os maiores custos por base?'},
                {'label': 'Ver inventários', 'pergunta': 'Quais inventários tiveram os maiores custos?'},
            ]
        else:
            detalhes = CustoInsumoService.por_inventario(
                qs,
                limite=limite,
                maiores=maiores,
            )
            linhas.extend([
                '',
                'DATA | CLIENTE | LOJA | BASE | TIPO | PESSOAS | CUSTO | CUSTO/PESSOA',
            ])
            for item in detalhes:
                custo_pessoa = item['custo_por_pessoa']
                linhas.append(
                    f'{item["inventario__data_inicio"]:%d/%m/%Y} | '
                    f'{item["inventario__cliente__sigla"]} | {item["inventario__loja"]} | '
                    f'{item["inventario__base__nome"]} | {item["inventario__tipo"] or "-"} | '
                    f'{item["inventario__pessoas"] or "-"} | R$ {cls._formatar_decimal(item["total"])} | '
                    f'{("R$ " + cls._formatar_decimal(custo_pessoa)) if custo_pessoa is not None else "-"}'
                )
            if resumo['inventarios'] > len(detalhes):
                linhas.extend([
                    '',
                    f'Exibindo {len(detalhes)} de {resumo["inventarios"]} inventários com consumo.',
                ])
            acoes = [
                {'label': 'Agrupar por base', 'pergunta': 'Quais bases possuem os maiores custos?'},
                {'label': 'Agrupar por cliente', 'pergunta': 'E os maiores custos por cliente?'},
            ]

        linhas.extend([
            '',
            'Os custos históricos usam o valor unitário gravado no momento do consumo; alterações de preço não reescrevem inventários anteriores.',
        ])
        resposta = cls._resposta('custos', '\n'.join(linhas))
        resposta['acoes'] = acoes
        return resposta

    @classmethod
    def _comparacao_precos(cls, user, interpretacao):
        from insumos.models import PrecoFornecedorInsumo, PesquisaPrecoOnline
        from insumos.services.custo_service import CustoInsumoService

        if not CustoInsumoService.pode_visualizar(user):
            return cls._resposta(
                'permissao',
                'as informações de preços e fornecedores não estão disponíveis para o seu perfil.'
            )
        if not interpretacao.insumo:
            return cls._resposta(
                'precos',
                'qual insumo você deseja comparar? Pode informar parte do nome, por exemplo: “toner”, “papel sulfite” ou “luva”.'
            )

        cotacoes = PrecoFornecedorInsumo.objects.filter(
            insumo=interpretacao.insumo,
            ativo=True,
        ).select_related('fornecedor').order_by(
            'fornecedor__nome', '-vigente_desde', '-criado_em'
        )
        por_fornecedor = {}
        for cotacao in cotacoes:
            por_fornecedor.setdefault(cotacao.fornecedor_id, cotacao)
        manuais = sorted(
            por_fornecedor.values(),
            key=lambda item: (item.valor_unitario, item.fornecedor.nome),
        )

        pesquisa = PesquisaPrecoOnline.objects.filter(insumo=interpretacao.insumo).first()
        online = list(pesquisa.ofertas.order_by('preco_total')[:10]) if pesquisa else []
        if not manuais and not online:
            return cls._resposta(
                'precos',
                f'ainda não há cotações ou ofertas pesquisadas para {interpretacao.insumo.descricao}. '
                'Compras pode cadastrar fornecedores e pesquisar preços na tela Pesquisa de preços.'
            )

        candidatos = [
            (item.valor_unitario, item.fornecedor.nome, 'cotação cadastrada')
            for item in manuais
        ] + [
            (item.preco_total, item.vendedor or item.fonte, 'oferta online')
            for item in online
        ]
        melhor = min(candidatos, key=lambda item: item[0])
        linhas = [
            f'Comparação de preços: {interpretacao.insumo.descricao}',
            '',
            f'- Melhor valor encontrado: R$ {cls._formatar_decimal(melhor[0])}',
            f'- Origem: {melhor[1]} ({melhor[2]})',
            f'- Fornecedores cadastrados comparados: {len(manuais)}',
            f'- Ofertas online comparadas: {len(online)}',
        ]
        if manuais:
            linhas.extend(['', 'FORNECEDOR | CNPJ | PREÇO | VIGÊNCIA'])
            for item in manuais[:10]:
                linhas.append(
                    f'{item.fornecedor.nome} | {item.fornecedor.cnpj_formatado} | '
                    f'R$ {cls._formatar_decimal(item.valor_unitario)} | {item.vigente_desde:%d/%m/%Y}'
                )
        if online:
            linhas.extend(['', 'OFERTA ONLINE | VENDEDOR | PREÇO | FRETE'])
            for item in online:
                frete = (
                    f'R$ {cls._formatar_decimal(item.frete)}'
                    if item.frete_conhecido else 'consultar'
                )
                linhas.append(
                    f'{item.titulo} | {item.vendedor or "-"} | '
                    f'R$ {cls._formatar_decimal(item.preco_total)} | {frete}'
                )
            if any(not item.frete_conhecido for item in online):
                linhas.extend([
                    '',
                    'Atenção: ofertas com frete desconhecido são comparadas pelo preço do produto; confirme o total antes da compra.',
                ])
        return cls._resposta('precos', '\n'.join(linhas))

    @classmethod
    def _solicitacoes_insumos(cls, user, interpretacao):
        from insumos.models import SolicitacaoInsumo

        perfil = getattr(user, 'perfil', None)
        pode_ver_todas = bool(perfil and (
            perfil.is_admin or perfil.is_compras_insumos or perfil.is_financeiro_insumos
        ))
        if not perfil or not (pode_ver_todas or perfil.is_gestor):
            return cls._resposta(
                'permissao',
                'o acompanhamento de solicitações de insumos não está disponível para o seu perfil.'
            )

        qs = SolicitacaoInsumo.objects.select_related('base', 'solicitante').prefetch_related(
            'itens__insumo'
        )
        if not pode_ver_todas:
            qs = qs.filter(solicitante=user)
        if interpretacao.protocolo:
            qs = qs.filter(protocolo__iexact=interpretacao.protocolo)
        solicitacoes = list(qs.order_by('-criado_em')[:10])
        if not solicitacoes:
            detalhe = f' com o protocolo {interpretacao.protocolo}' if interpretacao.protocolo else ''
            return cls._resposta(
                'solicitacoes_insumos',
                f'não encontrei solicitações de insumos{detalhe} dentro do seu acesso.'
            )

        linhas = [
            'Solicitações de insumos',
            '',
            'PROTOCOLO | DATA | BASE | SOLICITANTE | ITENS | PRIORIDADE | STATUS',
        ]
        for solicitacao in solicitacoes:
            itens = ', '.join(
                f'{item.insumo.descricao} ({cls._formatar_decimal(item.quantidade)})'
                for item in solicitacao.itens.all()
            )
            linhas.append(
                f'{solicitacao.protocolo} | {solicitacao.criado_em:%d/%m/%Y} | '
                f'{solicitacao.base.nome} | '
                f'{solicitacao.solicitante.get_full_name() or solicitacao.solicitante.get_username()} | '
                f'{itens} | {solicitacao.get_prioridade_display()} | {solicitacao.get_status_display()}'
            )
            if solicitacao.observacao_aprovacao:
                linhas.append(f'Observação: {solicitacao.observacao_aprovacao}')
        return cls._resposta('solicitacoes_insumos', '\n'.join(linhas))

    @classmethod
    def _testes_sistema(cls, user, interpretacao):
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        qs = secure_queryset_insumos(
            Inventario.objects.select_related('base', 'cliente'),
            user,
            campo_base='base',
        ).filter(base__in=cls._bases_visiveis(user))
        if interpretacao.base:
            qs = qs.filter(base=interpretacao.base)
        elif interpretacao.uf:
            qs = qs.filter(base__in=cls._bases_da_uf_visiveis(user, interpretacao.uf))
        elif interpretacao.grupo:
            qs = qs.filter(base__in=cls._bases_do_grupo_visiveis(user, interpretacao.grupo))
        if interpretacao.cliente:
            qs = qs.filter(cliente=interpretacao.cliente)
        if interpretacao.loja:
            qs = qs.filter(loja__iexact=interpretacao.loja)
        if interpretacao.periodo_inicio:
            qs = qs.filter(data_inicio__gte=interpretacao.periodo_inicio)
        if interpretacao.periodo_fim:
            qs = qs.filter(data_inicio__lte=interpretacao.periodo_fim)

        testes = []
        for inventario in qs.order_by('data_inicio', 'base__nome', 'cliente__sigla', 'loja'):
            marcacao = cls._dado_bruto(inventario, 'HORÁRIO DA VISITA')
            texto_marcacao = cls._normalizar(str(marcacao))
            if 'test sist' in texto_marcacao or 'teste sist' in texto_marcacao:
                testes.append((inventario, str(marcacao).strip()))

        escopo = cls._descricao_filtro_inventario(interpretacao)
        if not testes:
            return cls._resposta(
                'inventarios',
                f'não encontrei testes de sistema para {escopo} dentro das bases permitidas ao seu usuário.'
            )

        linhas = [
            f'Testes de sistema ({escopo})',
            '',
            f'- Testes encontrados: {len(testes)}',
            '',
            'CLIENTE | LOJA | DATA | BASE | TIPO | PESSOAS | MARCAÇÃO',
        ]
        for inventario, marcacao in testes[:20]:
            linhas.append(
                f'{inventario.cliente.sigla} | {inventario.loja} | {inventario.data_inicio:%d/%m/%Y} | '
                f'{inventario.base.nome} | {inventario.tipo or "-"} | '
                f'{cls._pessoas_inventario(inventario)} | {marcacao}'
            )
        if len(testes) > 20:
            linhas.extend(['', f'Exibindo 20 de {len(testes)} testes. Informe uma base ou período para refinar.'])
        return cls._resposta('inventarios', '\n'.join(linhas))

    @classmethod
    def _inventarios_por_grupo(cls, user, interpretacao):
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        bases = cls._bases_do_grupo_visiveis(user, interpretacao.grupo)
        qs = secure_queryset_insumos(
            Inventario.objects.select_related('base', 'cliente'),
            user,
            campo_base='base',
        ).filter(base__in=bases)

        if interpretacao.data:
            qs = qs.filter(data_inicio=interpretacao.data)

        inventarios = list(qs.order_by('base__nome', 'data_inicio', 'cliente__sigla', 'loja'))
        if not inventarios:
            filtro_data = f' em {interpretacao.data:%d/%m/%Y}' if interpretacao.data else ''
            return cls._resposta(
                'inventarios',
                f'nao encontrei inventarios do grupo regional {interpretacao.grupo.nome}{filtro_data} no seu escopo.'
            )

        pessoas_por_base = {}
        inventarios_por_base = {}
        for inv in inventarios:
            pessoas_por_base[inv.base_id] = pessoas_por_base.get(inv.base_id, 0) + cls._pessoas_inventario(inv)
            inventarios_por_base[inv.base_id] = inventarios_por_base.get(inv.base_id, 0) + 1

        linhas = [
            f'Resumo de inventarios do grupo regional {interpretacao.grupo.nome}:',
            '',
            f'- Bases do grupo no seu escopo: {len(bases)}',
            f'- Inventarios encontrados: {len(inventarios)}',
            f'- Pessoas previstas: {sum(pessoas_por_base.values())}',
            '',
            'BASE | INVENTÁRIOS | PESSOAS',
        ]
        for base in bases:
            linhas.append(
                f'{base.nome} | {inventarios_por_base.get(base.pk, 0)} | '
                f'{pessoas_por_base.get(base.pk, 0)}'
            )

        linhas.extend(['', 'PRIMEIROS INVENTÁRIOS | PESSOAS | STATUS | DATA'])
        for inv in inventarios[:10]:
            linhas.append(
                f'{inv.base.nome} - {inv.cliente.sigla} loja {inv.loja} | '
                f'{cls._pessoas_inventario(inv)} | {inv.status} | {inv.data_inicio:%d/%m/%Y}'
            )
        return cls._resposta('inventarios', '\n'.join(linhas))

    @classmethod
    def _capacidade_coletores_por_bases(cls, user, interpretacao):
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        if interpretacao.grupo:
            bases = cls._bases_do_grupo_visiveis(user, interpretacao.grupo)
            escopo = f'grupo regional {interpretacao.grupo.nome}'
        elif interpretacao.uf:
            bases = cls._bases_da_uf_visiveis(user, interpretacao.uf)
            escopo = f'UF {interpretacao.uf}'
        else:
            bases = cls._bases_visiveis(user)
            escopo = 'todas as bases do seu escopo'
        data_ref = interpretacao.data or timezone.localdate()
        inventarios = list(
            secure_queryset_insumos(
                Inventario.objects.select_related('base'),
                user,
                campo_base='base',
            ).filter(
                base__in=bases,
                data_inicio=data_ref,
            )
        )

        pessoas_por_base = {}
        inventarios_por_base = {}
        for inv in inventarios:
            pessoas_por_base[inv.base_id] = pessoas_por_base.get(inv.base_id, 0) + cls._pessoas_inventario(inv)
            inventarios_por_base[inv.base_id] = inventarios_por_base.get(inv.base_id, 0) + 1

        coletores_por_base = {
            item['regional_id']: item['total']
            for item in cls._equipamentos_visiveis(user).filter(
                regional__in=bases,
                produto__categoria__iexact='Coletores',
                status='ATIVO',
                finalidade=Equipamento.Finalidade.OPERACIONAL,
            ).values('regional_id').annotate(total=Count('id'))
        }

        atendem = 0
        nao_atendem = 0
        sem_inventario = 0
        linhas_base = []
        for base in bases:
            pessoas = pessoas_por_base.get(base.pk, 0)
            coletores = coletores_por_base.get(base.pk, 0)
            saldo = coletores - pessoas
            if not inventarios_por_base.get(base.pk, 0):
                sem_inventario += 1
                resultado = 'Sem inventario no dia'
            elif saldo >= 0:
                atendem += 1
                resultado = f'Atende, sobram {saldo}'
            else:
                nao_atendem += 1
                resultado = f'Nao atende, faltam {abs(saldo)}'

            linhas_base.append(
                f'{base.nome} | {inventarios_por_base.get(base.pk, 0)} | '
                f'{pessoas} | {coletores} | {resultado}'
            )

        linhas = [
            f'Analise de coletores de {escopo} em {data_ref:%d/%m/%Y}:',
            '',
            f'- Bases analisadas: {len(bases)}',
            f'- Bases que atendem: {atendem}',
            f'- Bases que nao atendem: {nao_atendem}',
            f'- Bases sem inventario no dia: {sem_inventario}',
            '',
            'BASE | INVENTÁRIOS | PESSOAS | COLETORES ATIVOS | RESULTADO',
            *linhas_base,
        ]
        return cls._resposta('capacidade', '\n'.join(linhas))

    @classmethod
    def _equipamentos_categoria(cls, user, interpretacao):
        qs = cls._equipamentos_visiveis(user).filter(produto__categoria=interpretacao.categoria)
        if interpretacao.base:
            qs = qs.filter(regional=interpretacao.base)
        elif interpretacao.uf:
            qs = qs.filter(regional__in=cls._bases_da_uf_visiveis(user, interpretacao.uf))
        if interpretacao.todas_bases or interpretacao.uf:
            return cls._equipamentos_categoria_por_base(user, interpretacao, qs)

        total = qs.count()
        ativos = qs.filter(
            status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL
        ).count()
        em_uso = qs.filter(status='EM_USO').count()
        sick = qs.filter(status='SICK').count()
        manutencao = qs.filter(status='MANUTENCAO').count()
        inativos = qs.filter(status='INATIVO').count()

        escopo = f' na base {interpretacao.base.nome}' if interpretacao.base else ''
        linhas = [
            f'{interpretacao.categoria}{escopo}',
            '',
            'TOTAL VISÍVEL | ATIVOS | EM USO | SICK | MANUTENÇÃO | INATIVOS',
            f'{total} | {ativos} | {em_uso} | {sick} | {manutencao} | {inativos}',
        ]

        por_produto = (
            qs.values('produto__descricao')
            .annotate(total=Count('id'))
            .order_by('-total', 'produto__descricao')[:10]
        )
        if por_produto:
            linhas.extend(['', 'MODELO/PRODUTO | QUANTIDADE | %'])
            for item in por_produto:
                participacao = Decimal(item['total'] * 100) / total if total else Decimal('0')
                linhas.append(
                    f'{item["produto__descricao"] or "-"} | {item["total"]} | '
                    f'{cls._formatar_decimal(participacao)}%'
                )
        return cls._resposta('estoque', '\n'.join(linhas))

    @classmethod
    def _equipamentos_categoria_por_base(cls, user, interpretacao, qs):
        if interpretacao.status:
            qs = qs.filter(status=interpretacao.status)

        totais_por_base = {
            item['regional_id']: item['total']
            for item in qs.values('regional_id')
            .annotate(total=Count('id'))
        }
        bases = cls._bases_do_escopo(user, interpretacao)
        if not bases:
            return cls._resposta(
                'estoque',
                'nao encontrei bases vinculadas ao seu usuario para listar.'
            )

        total = sum(totais_por_base.values())
        status_label = ' ativos' if interpretacao.status == 'ATIVO' else ''
        linhas = [
            f'Resumo de {interpretacao.categoria.lower()}{status_label} por base:',
            '',
            'BASES CONSULTADAS | TOTAL ENCONTRADO',
            f'{len(bases)} | {total}',
            '',
            'BASE | QUANTIDADE',
        ]
        linhas.extend(
            f'{base.nome} | {totais_por_base.get(base.pk, 0)}'
            for base in sorted(
                bases,
                key=lambda item: (-totais_por_base.get(item.pk, 0), item.nome),
            )
        )
        return cls._resposta('estoque', '\n'.join(linhas))

    @classmethod
    def _equipamentos(cls, user, interpretacao):
        qs = cls._equipamentos_visiveis(user)
        if interpretacao.base:
            qs = qs.filter(regional=interpretacao.base)
        elif interpretacao.uf:
            qs = qs.filter(regional__in=cls._bases_da_uf_visiveis(user, interpretacao.uf))

        total = qs.count()
        por_status = qs.values('status').annotate(total=Count('id')).order_by('-total')[:8]
        por_categoria = qs.values('produto__categoria').annotate(total=Count('id')).order_by('-total')
        escopo = cls._descricao_escopo_geografico(interpretacao, prefixo=' em')

        linhas = [
            'Resumo de equipamentos',
            '',
            'ESCOPO | TOTAL VISÍVEL',
            f'{escopo.strip() or "Seu escopo de acesso"} | {total}',
        ]
        if por_status:
            linhas.extend(['', 'STATUS | QUANTIDADE | %'])
            for item in por_status:
                participacao = Decimal(item['total'] * 100) / total if total else Decimal('0')
                linhas.append(
                    f'{item["status"] or "-"} | {item["total"]} | '
                    f'{cls._formatar_decimal(participacao)}%'
                )
        if por_categoria:
            linhas.extend(['', 'CATEGORIA | QUANTIDADE | %'])
            for item in por_categoria:
                participacao = Decimal(item['total'] * 100) / total if total else Decimal('0')
                linhas.append(
                    f'{item["produto__categoria"] or "-"} | {item["total"]} | '
                    f'{cls._formatar_decimal(participacao)}%'
                )
        return cls._resposta('estoque', '\n'.join(linhas))

    @classmethod
    def _insumos(cls, user, interpretacao):
        from insumos.models import MovimentacaoInsumo
        from insumos.utils import secure_queryset_insumos

        qs = secure_queryset_insumos(
            MovimentacaoInsumo.objects.select_related('base', 'insumo', 'insumo__categoria'),
            user,
            campo_base='base',
        )
        if interpretacao.base:
            qs = qs.filter(base=interpretacao.base)
        elif interpretacao.uf:
            qs = qs.filter(base__in=cls._bases_da_uf_visiveis(user, interpretacao.uf))

        saldos = (
            qs.values('insumo__descricao')
            .annotate(
                entradas=Sum(
                    Case(
                        When(tipo__in=cls.ENTRADAS_INSUMO, then='quantidade'),
                        default=Value(Decimal('0')),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                ),
                saidas=Sum(
                    Case(
                        When(tipo__in=cls.SAIDAS_INSUMO, then='quantidade'),
                        default=Value(Decimal('0')),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                ),
            )
            .order_by('insumo__descricao')
        )
        resumo = []
        for item in saldos[:8]:
            saldo = (item['entradas'] or Decimal('0')) - (item['saidas'] or Decimal('0'))
            resumo.append(f"{item['insumo__descricao']}: {saldo}")

        escopo = cls._descricao_escopo_geografico(interpretacao, prefixo=' para')
        texto = f'Encontrei {qs.count()} movimentacao(oes) de insumos{escopo} no seu escopo.'
        texto += '\nSaldos calculados: ' + '; '.join(resumo) if resumo else '\nNao ha movimentacoes de insumos visiveis para esse filtro.'
        return cls._resposta('insumos', texto)

    @classmethod
    def _transferencias(cls, user, interpretacao):
        qs = cls._transferencias_visiveis(user)
        if interpretacao.base:
            qs = qs.filter(Q(regional_origem=interpretacao.base) | Q(regional_destino=interpretacao.base))
        elif interpretacao.uf:
            bases_uf = cls._bases_da_uf_visiveis(user, interpretacao.uf)
            qs = qs.filter(Q(regional_origem__in=bases_uf) | Q(regional_destino__in=bases_uf))
        if interpretacao.protocolo:
            qs = qs.filter(protocolo__icontains=interpretacao.protocolo)

        if interpretacao.protocolo:
            itens = qs.select_related('regional_origem', 'regional_destino').prefetch_related('itens')[:5]
            if not itens:
                return cls._resposta('transferencias', f'Nao encontrei transferencia com protocolo parecido com {interpretacao.protocolo} no seu escopo.')
            linhas = []
            for t in itens:
                linhas.append(
                    f'{t.protocolo}: {t.regional_origem.nome} -> {t.regional_destino.nome}, '
                    f'status {t.status}, {t.itens.count()} item(ns).'
                )
            return cls._resposta('transferencias', '\n'.join(linhas))

        total = qs.count()
        por_status = qs.values('status').annotate(total=Count('id')).order_by('-total')
        texto = f'Voce possui {total} transferencia(s) visiveis.'
        if por_status:
            texto += '\nPor status: ' + cls._formatar_grupo(por_status, 'status')
        return cls._resposta('transferencias', texto)

    @classmethod
    def _historico(cls, user, interpretacao):
        qs = secure_queryset(
            Historico.objects.select_related('equipamento', 'equipamento__produto', 'usuario'),
            user,
            campo_empresa='equipamento__regional__empresa',
            campo_regional='equipamento__regional',
        )
        if interpretacao.protocolo:
            qs = qs.filter(detalhes__protocolo__icontains=interpretacao.protocolo)
        if interpretacao.base:
            qs = qs.filter(equipamento__regional=interpretacao.base)
        elif interpretacao.uf:
            qs = qs.filter(equipamento__regional__in=cls._bases_da_uf_visiveis(user, interpretacao.uf))

        ultimos = qs.order_by('-data')[:5]
        if not ultimos:
            return cls._resposta('historico', 'Nao encontrei historico para esse filtro no seu escopo.')

        linhas = []
        for h in ultimos:
            protocolo = (h.detalhes or {}).get('protocolo', '-')
            produto = h.equipamento.produto.descricao if h.equipamento and h.equipamento.produto else '-'
            linhas.append(f'{h.data:%d/%m/%Y %H:%M} | {h.tipo_acao} | {produto} | protocolo {protocolo}')
        return cls._resposta('historico', '\n'.join(linhas))

    @classmethod
    def _inventarios_checklists(cls, user, interpretacao):
        from insumos.models import ChecklistDiario, Inventario
        from insumos.utils import secure_queryset_insumos

        inventarios = secure_queryset_insumos(
            Inventario.objects.select_related('base', 'cliente'),
            user,
            campo_base='base',
        )
        if interpretacao.base:
            inventarios = inventarios.filter(base=interpretacao.base)
        elif interpretacao.uf:
            inventarios = inventarios.filter(base__in=cls._bases_da_uf_visiveis(user, interpretacao.uf))
        if interpretacao.data:
            inventarios = inventarios.filter(data_inicio=interpretacao.data)

        checklists = ChecklistDiario.objects.select_related('inventario__base', 'inventario__cliente')
        if not user.perfil.is_admin:
            checklists = checklists.filter(inventario__base__in=user.perfil.regionais.all())
        if interpretacao.base:
            checklists = checklists.filter(inventario__base=interpretacao.base)
        elif interpretacao.uf:
            checklists = checklists.filter(inventario__base__in=cls._bases_da_uf_visiveis(user, interpretacao.uf))
        if interpretacao.data:
            checklists = checklists.filter(inventario__data_inicio=interpretacao.data)

        inv_status = inventarios.values('status').annotate(total=Count('id')).order_by('-total')
        chk_status = checklists.values('status').annotate(total=Count('id')).order_by('-total')

        texto = f'Inventarios visiveis: {inventarios.count()}\nChecklists visiveis: {checklists.count()}'
        if inv_status:
            texto += '\nInventarios por status: ' + cls._formatar_grupo(inv_status, 'status')
        if chk_status:
            texto += '\nChecklists por status: ' + cls._formatar_grupo(chk_status, 'status')
        return cls._resposta('inventarios_checklists', texto)

    @classmethod
    def _indicadores(cls, user, interpretacao):
        partes = [
            cls._equipamentos(user, interpretacao)['resposta'],
            cls._transferencias(user, interpretacao)['resposta'],
            cls._inventarios_checklists(user, interpretacao)['resposta'],
        ]
        return cls._resposta('indicadores', '\n\n'.join(partes))

    @classmethod
    def _escolher_base(cls, user, interpretacao):
        opcoes = interpretacao.opcoes_base or [base.nome for base in cls._bases_visiveis(user)]
        if not opcoes:
            return cls._resposta(
                'permissao',
                'nao encontrei nenhuma base vinculada ao seu usuario para consultar agora.'
            )

        limite = 20
        sao_paulo_ambiguo = bool(
            interpretacao.opcoes_base and re.search(r'\bsao paulo\b', interpretacao.texto)
        )
        if sao_paulo_ambiguo:
            base_exata = next(
                (nome for nome in opcoes if cls._normalizar(nome) == 'sao paulo'),
                'SÃO PAULO',
            )
            linhas = [
                '“São Paulo” pode significar uma base específica ou todo o estado. Escolha o escopo:',
                '',
                'OPÇÃO | ESCOPO CONSULTADO | COMO PEDIR',
                f'Base {base_exata} | Somente essa base | Na base {base_exata}',
                'Estado de São Paulo | Todas as bases de SP permitidas ao seu perfil | UF SP',
                f'Outra base específica | Uma das outras {max(len(opcoes) - 1, 0)} bases disponíveis | Na base NOME DA BASE',
            ]
        else:
            linhas = [
                'só preciso confirmar qual base você deseja consultar.',
                '',
                'OPÇÃO | BASE | COMO PEDIR',
            ]
            linhas.extend(
                f'{indice} | {nome} | Na base {nome}'
                for indice, nome in enumerate(opcoes[:limite], start=1)
            )
            if len(opcoes) > limite:
                linhas.append(f'… | Mais {len(opcoes) - limite} base(s) | Digite o nome da base')
        if sao_paulo_ambiguo:
            linhas.extend([
                '',
                'Se quiser outra base, escreva o nome completo; eu preservo a pergunta original.',
            ])
        return cls._resposta('escolher_base', '\n'.join(linhas))

    @classmethod
    def _base_sem_acesso(cls, user, interpretacao):
        return cls._resposta(
            'permissao',
            f'nao posso consultar a base {interpretacao.base_bloqueada}, porque ela nao esta vinculada ao seu usuario.'
        )

    @classmethod
    def _grupo_sem_acesso(cls, user, interpretacao):
        return cls._resposta(
            'permissao',
            f'nao posso consultar o grupo regional {interpretacao.grupo_bloqueado}, porque ele nao possui bases vinculadas ao seu usuario.'
        )

    @classmethod
    def _uf_sem_acesso(cls, user, interpretacao):
        return cls._resposta(
            'permissao',
            f'não posso consultar a UF {interpretacao.uf_bloqueada}, porque não há bases dessa UF vinculadas ao seu usuário.'
        )

    @classmethod
    def _orientacao(cls, user, interpretacao):
        return cls._resposta(
            'orientacao',
            (
                'Posso ajudar com perguntas como:\n'
                '- Quantos coletores ativos existem na minha base?\n'
                '- Inventarios de hoje.\n'
                '- A minha base atende 18 pessoas com coletores hoje?\n'
                #'- Inventarios do Grupo Regional Sul.\n'
                #'- As bases do Grupo Regional Sul atendem os inventarios com coletores hoje?\n'
                '- Como cadastrar um router?\n'
                '- Como marcar um equipamento como SICK?\n'
                '- Como fazer um empréstimo?\n'
                #'- Status da transferencia pelo protocolo informado.\n'
                '- Resumo de insumos da minha base.'
            )
        )

    @classmethod
    def _saudacao(cls, user, interpretacao):
        texto = interpretacao.texto
        espanhol = getattr(getattr(user, 'perfil', None), 'idioma', '') == 'es'
        if espanhol:
            if 'buenos dias' in texto:
                abertura = '¡Buenos días!'
            elif 'buenas tardes' in texto:
                abertura = '¡Buenas tardes!'
            elif 'buenas noches' in texto:
                abertura = '¡Buenas noches!'
            elif re.search(r'\bhola\b', texto):
                abertura = '¡Hola!'
            else:
                abertura = '¡Hola!'
            if cls._tem(texto, 'como estas', 'como esta', 'todo bien'):
                complemento = f'Soy {cls.NOME_ASSISTENTE}. Estoy bien y lista para ayudar. ¿Y usted, cómo está?'
            else:
                complemento = f'Soy {cls.NOME_ASSISTENTE}, ¿cómo puedo ayudarle? ¿Qué le gustaría saber?'
            return cls._resposta('saudacao', f'{abertura} {complemento}')

        if 'bom dia' in texto:
            abertura = 'Bom dia!'
        elif 'boa tarde' in texto:
            abertura = 'Boa tarde!'
        elif 'boa noite' in texto:
            abertura = 'Boa noite!'
        elif re.search(r'\bsalve\b', texto):
            abertura = 'Salve!'
        elif re.search(r'\be\s*(?:ai|ae)\b|\beai\b', texto):
            abertura = 'E aí!'
        elif re.search(r'\bola\b', texto):
            abertura = 'Olá!'
        elif re.search(r'\boi\b', texto):
            abertura = 'Oi!'
        else:
            abertura = ''

        pergunta_como_esta = cls._tem(
            texto, 'como vai', 'como voce esta', 'como esta voce', 'tudo bem', 'ta tudo bem'
        )
        if pergunta_como_esta:
            complemento = 'Estou bem e por aqui para ajudar. E você, como está?'
        else:
            complemento = (
                'Estou por aqui. Posso analisar planejamento, execução, estoque, insumos e custos '
                'dentro do seu acesso. O que você quer verificar?'
            )
        return cls._resposta(
            'saudacao',
            f'{abertura} {complemento}'.strip()
        )

    @classmethod
    def _ajuda_sistema(cls, user, interpretacao):
        texto = interpretacao.texto
        perfil = getattr(user, 'perfil', None)
        role = getattr(perfil, 'role', '')
        espanhol = getattr(perfil, 'idioma', '') == 'es'

        if cls._tem(texto, 'sick'):
            if role not in {'admin', 'gestor'}:
                return cls._resposta(
                    'ajuda',
                    'para marcar um equipamento como SICK, seu perfil precisa ter acesso à tela de Estoque. '
                    'No momento essa ação não aparece no seu menu; solicite a um gestor ou administrador da sua base.'
                )
            return cls._resposta(
                'ajuda',
                'para marcar um equipamento como SICK:\n\n'
                '1. Abra Estoque no menu.\n'
                '2. Localize a base e o produto do equipamento.\n'
                '3. Abra a lista de equipamentos e encontre a série ou o patrimônio.\n'
                '4. Clique em SICK na linha do equipamento.\n'
                '5. Informe o motivo do problema e clique em Confirmar SICK.\n\n'
                'O sistema altera o status e registra a ação no histórico. Equipamentos inativos, em trânsito, '
                'em transferência ou que já estejam em SICK não podem ser marcados novamente.'
            )

        if cls._tem(texto, 'emprestimo', 'emprestar'):
            if cls._tem(texto, 'receber', 'recebimento', 'confirmar recebimento'):
                return cls._resposta(
                    'ajuda',
                    'para receber um empréstimo:\n\n'
                    '1. Abra Transferências > Empréstimos.\n'
                    '2. Localize e abra o protocolo aguardando recebimento.\n'
                    '3. Clique em Confirmar Recebimento.\n'
                    '4. Confira e marque os itens que chegaram.\n'
                    '5. Confirme a operação.\n\n'
                    'Essa ação fica disponível para usuários vinculados à base de destino. Divergências devem ser registradas na conferência.'
                )
            if cls._tem(texto, 'devolver', 'devolucao', 'devolução'):
                return cls._resposta(
                    'ajuda',
                    'para devolver um empréstimo:\n\n'
                    '1. Abra Transferências > Empréstimos e entre no protocolo.\n'
                    '2. Clique em Devolver Equipamentos.\n'
                    '3. Marque os itens devolvidos e confirme.\n'
                    '4. A base de origem deverá conferir e confirmar a devolução.\n\n'
                    'O empréstimo só é finalizado depois que a base de origem confirma os itens recebidos de volta.'
                )
            return cls._resposta(
                'ajuda',
                'para criar um empréstimo:\n\n'
                '1. Abra Movimentações > Empréstimos.\n'
                '2. Clique em Novo Empréstimo.\n'
                '3. Escolha uma base de origem vinculada ao seu usuário.\n'
                '4. Escolha a base de destino, que deve pertencer ao mesmo Grupo Regional da origem.\n'
                '5. Informe a data prevista de devolução e o motivo.\n'
                '6. Filtre e marque um ou mais equipamentos ativos.\n'
                '7. Clique em Criar empréstimo.\n\n'
                'Depois disso, o sistema gera um protocolo e a base de destino acompanha o recebimento. '
                'Somente equipamentos ativos da base de origem ficam disponíveis para seleção.'
            )

        if cls._tem(texto, 'insumo', 'insumos', 'material', 'materiais') and cls._tem(
            texto, 'solicitar', 'solicitacao', 'pedido', 'pedir'
        ):
            if role not in {'admin', 'gestor'}:
                return cls._resposta(
                    'ajuda',
                    'seu perfil acompanha solicitações de insumos, mas não cria pedidos. '
                    'A criação fica disponível para gestores e administradores.'
                )
            return cls._resposta(
                'ajuda',
                'para solicitar insumos:\n\n'
                '1. Abra Solicitações de insumos no menu.\n'
                '2. Clique em Nova solicitação.\n'
                '3. Selecione a base e a prioridade.\n'
                '4. Escolha um insumo, informe a quantidade e clique em Adicionar.\n'
                '5. Repita para incluir outros itens no carrinho.\n'
                '6. Revise as quantidades, informe a justificativa e clique em Enviar solicitação.\n\n'
                'Tory também pode consultar o andamento pelo protocolo. Compras ou Admin analisa o pedido, '
                'e Gestor, Compras, Admin e Financeiro recebem os comunicados das mudanças.'
            )

        if cls._tem(texto, 'transferencia', 'transferir', 'solicitacao', 'solicitar equipamento'):
            if role == 'gestor':
                return cls._resposta(
                    'ajuda',
                    'para solicitar uma transferência de equipamentos:\n\n'
                    '1. Abra Solicitar no menu.\n'
                    '2. Escolha sua base, se houver mais de uma vinculada.\n'
                    '3. Selecione o tipo de equipamento e informe a quantidade.\n'
                    '4. Descreva o motivo e clique em Enviar Solicitação.\n\n'
                    'O pedido segue para análise e, após a aprovação, aparece no fluxo de Separação e Recebimentos.'
                )
            return cls._resposta(
                'ajuda',
                'as transferências seguem três etapas no menu Transferências: Pedidos, Separação e Recebimentos. '
                'O gestor da base cria a solicitação; o responsável aprova e separa os equipamentos; por fim, '
                'a base de destino confere cada item e registra qualquer divergência ou observação antes de confirmar.'
            )

        if cls._tem(texto, 'insumo', 'insumos', 'material', 'materiais') and cls._tem(
            texto, 'cadastrar', 'cadastro', 'registrar', 'entrada', 'adicionar', 'incluir'
        ):
            if role not in {'admin', 'gestor'}:
                return cls._resposta(
                    'ajuda',
                    'a entrada de insumos fica em Cadastros > Insumos e não aparece no menu do seu perfil. '
                    'Solicite o registro a um gestor ou administrador da sua base.'
                )
            return cls._resposta(
                'ajuda',
                'para registrar a entrada de um insumo:\n\n'
                '1. Abra Cadastros > Insumos.\n'
                '2. Selecione uma das bases vinculadas ao seu usuário.\n'
                '3. Escolha a categoria do material.\n'
                '4. Selecione o insumo na lista carregada para essa categoria.\n'
                '5. Informe a quantidade recebida.\n'
                '6. Clique em Salvar, confira os dados e escolha Confirmar e Salvar.\n\n'
                'Essa operação adiciona quantidade ao estoque e fica registrada como entrada. '
                'Ela não cria um novo tipo de insumo. Se o material não aparecer na lista, o cadastro mestre precisa ser criado ou ativado pelo administrador.'
            )

        if cls._tem(texto, 'checklist', 'checklists'):
            return cls._resposta(
                'ajuda',
                'para preencher o retorno de um checklist:\n\n'
                '1. Abra Checklist > Lista de Checklists.\n'
                '2. Localize o inventário e clique em Retorno.\n'
                '3. Em Insumos, informe quanto retornou; o sistema calcula automaticamente quanto foi utilizado.\n'
                '4. Em Equipamentos, informe a quantidade retornada de cada categoria.\n'
                '5. Se houver diferença, marque exatamente os equipamentos com ocorrência, selecione SICK, Dano, Perda ou Roubo e escreva a observação.\n'
                '6. Em TAGs, informe o último número utilizado de cada lote ou rolo.\n'
                '7. Use Salvar retorno para continuar depois ou Salvar e finalizar quando toda a conferência estiver concluída.\n\n'
                'Você só pode consultar checklists das suas bases. A finalização é permitida para administrador, gestor ou usuário responsável pelo checklist.'
            )

        if cls._tem(texto, 'equipamento', 'equipamentos', 'router', 'roteador', 'coletor', 'notebook', 'impressora') and cls._tem(
            texto, 'cadastrar', 'cadastro', 'registrar', 'adicionar', 'incluir'
        ):
            categoria = cls._extrair_categoria(texto)
            categoria_texto = f' da categoria {categoria}' if categoria else ''
            if role not in {'admin', 'gestor'}:
                if espanhol:
                    return cls._resposta(
                        'ajuda',
                        'el registro de equipos está en Registros > Equipos y no está disponible para su perfil. '
                        'Solicite el registro a un gestor o administrador de su base.'
                    )
                return cls._resposta(
                    'ajuda',
                    'o cadastro de equipamentos fica em Cadastros > Equipamentos e não está disponível no menu do seu perfil. '
                    'Solicite o cadastro a um gestor ou administrador da sua base.'
                )
            if espanhol:
                return cls._resposta(
                    'ajuda',
                    'para registrar un equipo:\n\n'
                    '1. Abra Registros > Equipos.\n'
                    '2. Seleccione la categoría correcta.\n'
                    '3. Seleccione el producto o modelo correspondiente.\n'
                    '4. Informe el número de serie, patrimonio, base y responsable.\n'
                    '5. Agregue una foto, si lo desea.\n'
                    '6. Haga clic en Guardar, revise los datos y seleccione Confirmar y guardar.\n\n'
                    'El número de serie y el patrimonio no pueden estar registrados en otro equipo. '
                    'Si el producto no aparece, solicite primero su registro al administrador.'
                )
            return cls._resposta(
                'ajuda',
                f'para cadastrar um equipamento{categoria_texto}:\n\n'
                '1. Abra Cadastros > Equipamentos.\n'
                f'2. Escolha a categoria{f" {categoria}" if categoria else " correta"}.\n'
                '3. Selecione o produto/modelo correspondente.\n'
                '4. Informe número de série, patrimônio, base e responsável.\n'
                '5. Adicione uma foto, se desejar.\n'
                '6. Clique em Salvar, confira os dados e escolha Confirmar e Salvar.\n\n'
                'A série e o patrimônio não podem estar cadastrados em outro equipamento. '
                'Se o produto/modelo não aparecer após selecionar a categoria, peça ao administrador para cadastrá-lo primeiro.'
            )

        if espanhol:
            return cls._resposta(
                'ajuda',
                'puedo explicar los procedimientos del sistema paso a paso. Por ejemplo:\n'
                '- ¿Cómo registrar un colector, router, notebook o impresora?\n'
                '- ¿Cómo marcar un equipo como SICK?\n'
                '- ¿Cómo crear, recibir o devolver un préstamo?\n'
                '- ¿Cómo realizar una transferencia?\n'
                '- ¿Cómo consultar inventarios, checklists o historiales?\n\n'
                'Dígame qué necesita hacer, aunque no conozca el nombre exacto de la pantalla.'
            )
        return cls._resposta(
            'ajuda',
            'posso explicar as rotinas do sistema passo a passo. Por exemplo:\n'
            '- Como cadastrar um coletor, router, notebook ou impressora?\n'
            '- Como marcar um equipamento como SICK?\n'
            '- Como criar, receber ou devolver um empréstimo?\n'
            '- Como fazer uma transferência?\n'
            '- Como consultar inventários, checklists ou histórico?\n\n'
            'Diga o que você precisa fazer, mesmo que não saiba o nome exato da tela.'
        )

    @classmethod
    def _explicar_termo(cls, user, interpretacao):
        texto = interpretacao.texto

        if cls._tem(texto, 'diferenca', 'diferença') and cls._tem(texto, 'emprestimo') and cls._tem(texto, 'transferencia'):
            return cls._resposta(
                'glossario',
                'a diferença é esta:\n\n'
                'EMPRÉSTIMO | TRANSFERÊNCIA\n'
                'Temporário | Definitiva entre bases\n'
                'Possui data prevista de devolução | Não possui devolução prevista\n'
                'O equipamento deve retornar à origem | O equipamento passa a pertencer à base de destino\n'
                'Use quando a necessidade tem prazo | Use quando a mudança de base é permanente'
            )

        if cls._tem(texto, 'sick'):
            return cls._resposta(
                'glossario',
                'SICK é o status usado quando um equipamento apresenta defeito, dano ou problema operacional. '
                'Enquanto estiver em SICK, ele não deve ser considerado disponível. O motivo fica registrado no histórico até a resolução.'
            )
        if cls._tem(texto, 'checklist', 'checklists'):
            return cls._resposta(
                'glossario',
                'checklist é a conferência operacional de um inventário. Ele registra os equipamentos, insumos e TAGs enviados, '
                'o que retornou, o que foi utilizado e qualquer ocorrência, como SICK, dano, perda ou roubo.'
            )
        if cls._tem(texto, 'inventario', 'inventarios'):
            return cls._resposta(
                'glossario',
                'inventário é o trabalho programado para uma loja ou cliente em determinada data. No sistema ele informa, entre outros dados, '
                'a base responsável, o status e a quantidade de pessoas previstas para executar o serviço.'
            )
        if cls._tem(texto, 'insumo', 'insumos', 'material', 'materiais'):
            return cls._resposta(
                'glossario',
                'insumo é um material consumível ou controlado pelo estoque, como etiquetas e outros itens usados na operação. '
                'As entradas, saídas, devoluções e ajustes formam o saldo de cada base.'
            )
        if cls._tem(texto, 'coletor', 'coletores', 'maquininha', 'maquininhas'):
            return cls._resposta(
                'glossario',
                'coletor é o equipamento usado pelas pessoas durante o inventário para registrar os dados. '
                'Na análise de capacidade, o sistema compara um coletor ATIVO para cada pessoa prevista.'
            )
        if cls._tem(texto, 'emprestimo', 'emprestimos'):
            return cls._resposta(
                'glossario',
                'empréstimo é o envio temporário de equipamentos entre bases do mesmo Grupo Regional. '
                'Ele possui origem, destino, motivo, prazo de devolução e protocolo, e termina depois que a origem confirma o retorno.'
            )
        if cls._tem(texto, 'transferencia', 'transferencias'):
            return cls._resposta(
                'glossario',
                'transferência é a mudança definitiva de um equipamento para outra base. '
                'Após separação, envio e recebimento, o equipamento passa a ficar vinculado à base de destino.'
            )
        if cls._tem(texto, 'protocolo', 'protocolos'):
            return cls._resposta(
                'glossario',
                'protocolo é o identificador de uma operação. Ele permite localizar transferências, empréstimos, comunicados e registros do histórico '
                'sem depender do nome do equipamento ou do usuário.'
            )
        if cls._tem(texto, 'patrimonio', 'patrimônio'):
            return cls._resposta(
                'glossario',
                'patrimônio é o número de controle interno atribuído ao equipamento pela empresa. '
                'Ele não é o mesmo que o número de série do fabricante e não pode se repetir no cadastro.'
            )
        if cls._tem(texto, 'numero de serie', 'número de série', 'serie'):
            return cls._resposta(
                'glossario',
                'número de série é a identificação única fornecida pelo fabricante. '
                'No sistema, ele ajuda a identificar fisicamente o equipamento e não pode estar cadastrado em duplicidade.'
            )
        if cls._tem(texto, 'grupo regional', 'regional sul', 'grupo'):
            return cls._resposta(
                'glossario',
                'Grupo Regional é um conjunto de bases relacionadas operacionalmente. Ele permite consultar indicadores em grupo '
                'e determina, por exemplo, quais bases podem participar de um empréstimo entre si.'
            )
        if cls._tem(texto, 'base', 'regional'):
            return cls._resposta(
                'glossario',
                'base, também chamada de regional em algumas telas, é a unidade operacional onde equipamentos e insumos ficam vinculados. '
                'O usuário só pode consultar as bases permitidas no seu cadastro.'
            )
        if re.search(r'\b(todas|todos)\b', texto):
            return cls._resposta(
                'glossario',
                'TODAS não é uma base. Nos arquivos de inventário, é um marcador indicando que a operação pode precisar do conjunto de bases. '
                'No chat, responder “todas” significa consultar todas as bases permitidas para o seu usuário.'
            )
        if cls._tem(texto, 'em transito', 'trânsito'):
            return cls._resposta(
                'glossario',
                'EM TRÂNSITO significa que o equipamento já saiu da origem, mas o recebimento ainda não foi confirmado pela base de destino. '
                'Nesse período ele não deve ser contado como disponível em nenhuma das duas bases.'
            )
        if re.search(r'\bativo|ativos\b', texto):
            return cls._resposta(
                'glossario',
                'ATIVO significa que o equipamento está operacional e disponível para uso. '
                'É esse status que entra no cálculo de capacidade para atender as pessoas dos inventários.'
            )
        if cls._tem(texto, 'em uso'):
            return cls._resposta(
                'glossario',
                'EM USO significa que o equipamento está operacional, mas já está alocado ou sendo utilizado. '
                'Por isso ele aparece no estoque, porém não é contado como disponível na análise do dia.'
            )
        if cls._tem(texto, 'manutencao'):
            return cls._resposta(
                'glossario',
                'MANUTENÇÃO significa que o equipamento está em reparo ou tratamento técnico. '
                'Ele permanece indisponível até que o status seja atualizado após a conclusão do serviço.'
            )
        if cls._tem(texto, 'pessoas previstas', 'pessoas'):
            return cls._resposta(
                'glossario',
                'pessoas previstas é a quantidade de integrantes planejada para executar o inventário. '
                'Esse número vem do arquivo importado e é comparado com os coletores ativos da base.'
            )
        if cls._tem(texto, 'tag', 'tags'):
            return cls._resposta(
                'glossario',
                'TAG é uma etiqueta numerada controlada por lote ou rolo. No checklist são registrados o intervalo enviado, '
                'o último número utilizado e a quantidade consumida.'
            )

        return cls._resposta(
            'glossario',
            'não reconheci qual termo você quer entender. Escreva apenas o nome ou use uma frase como “o que significa EM TRÂNSITO?”.'
        )

    @classmethod
    def _equipamentos_visiveis(cls, user):
        return secure_queryset(
            Equipamento.objects.select_related('produto', 'regional'),
            user,
            campo_empresa='regional__empresa',
            campo_regional='regional',
        )

    @classmethod
    def _transferencias_visiveis(cls, user):
        perfil = user.perfil
        qs = Transferencia.objects.all()
        if perfil.is_admin:
            return qs
        return qs.filter(
            Q(regional_origem__in=perfil.regionais.all()) |
            Q(regional_destino__in=perfil.regionais.all())
        )

    @classmethod
    def _extrair_categoria(cls, texto):
        for termo, categoria in cls.CATEGORIAS.items():
            if re.search(rf'\b{re.escape(termo)}\b', texto):
                return categoria
        return ''

    @classmethod
    def _extrair_base(cls, user, texto):
        return cls._resolver_base(cls._bases_visiveis(user), texto)

    @classmethod
    def _extrair_base_global(cls, texto):
        return cls._resolver_base(Base.objects.all().order_by('nome'), texto)

    @classmethod
    def _extrair_uf(cls, texto):
        siglas_diretas = {'SP', 'RJ', 'PR', 'SC', 'RS', 'MG', 'DF'}
        for alias, uf in sorted(cls.UF_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
            if not re.search(rf'\b{re.escape(alias)}\b', texto):
                continue
            if len(alias) == 2 and uf not in siglas_diretas:
                if not re.search(rf'\b(?:em|no|na|do|da|uf|estado)\s+(?:de\s+|do\s+|da\s+)?{re.escape(alias)}\b', texto):
                    continue
            if alias == 'para' and not re.search(r'\b(?:no|do|estado do)\s+para\b', texto):
                continue
            return uf
        return ''

    @classmethod
    def _resolver_base(cls, bases, texto):
        bases = [base for base in bases if cls._base_operacional(base)]
        for alias, nome_base in cls.BASE_ALIASES.items():
            if re.search(rf'\b{re.escape(alias)}\b', texto):
                base_alias = next(
                    (base for base in bases if cls._normalizar(base.nome) == cls._normalizar(nome_base)),
                    None,
                )
                if base_alias:
                    return base_alias

        for base in sorted(bases, key=lambda item: len(item.nome), reverse=True):
            nome = cls._normalizar(base.nome)
            if nome and re.search(rf'\b{re.escape(nome)}\b', texto):
                return base

        palavras_pergunta = re.findall(r'[a-z0-9]+', texto)
        ignorar = {
            'base', 'bases', 'de', 'da', 'do', 'das', 'dos', 'em', 'para', 'tem',
            'sp', 'pr', 'rj', 'sc', 'int', 'oxxo', 'regional', 'grupo', 'hoje',
            'equipamento', 'equipamentos', 'inventario', 'inventarios', 'atende',
        }
        palavras_pergunta = [p for p in palavras_pergunta if len(p) >= 4 and p not in ignorar]
        candidatos = []
        for base in bases:
            palavras_base = [
                p for p in re.findall(r'[a-z0-9]+', cls._normalizar(base.nome))
                if len(p) >= 4 and p not in ignorar
            ]
            if not palavras_base:
                continue
            melhor = max(
                (SequenceMatcher(None, pergunta, nome).ratio()
                 for pergunta in palavras_pergunta for nome in palavras_base),
                default=0,
            )
            if melhor >= 0.78:
                candidatos.append((melhor, base))

        candidatos.sort(key=lambda item: (-item[0], len(item[1].nome)))
        if not candidatos:
            return None
        if len(candidatos) > 1 and candidatos[0][0] == candidatos[1][0]:
            return None
        return candidatos[0][1]

    @classmethod
    def _extrair_grupo_global(cls, texto):
        for alias, nome in cls.GRUPO_ALIASES.items():
            if re.search(rf'\b{re.escape(alias)}\b', texto):
                grupo = GrupoRegional.objects.filter(nome__iexact=nome, ativo=True).first()
                if grupo:
                    return grupo
        if cls._melhor_similaridade_token(texto, 'oxxo') >= 0.82:
            regioes = {
                'interior': 'OXXO INTERIOR',
                'leste': 'OXXO LESTE',
                'sul': 'OXXO SUL/LITORAL',
                'litoral': 'OXXO SUL/LITORAL',
            }
            candidatos = [
                (cls._melhor_similaridade_token(texto, termo), nome)
                for termo, nome in regioes.items()
            ]
            score, nome = max(candidatos, default=(0, ''))
            if score >= 0.78:
                grupo = GrupoRegional.objects.filter(nome__iexact=nome, ativo=True).first()
                if grupo:
                    return grupo
        for grupo in GrupoRegional.objects.filter(ativo=True).order_by('-nome'):
            nome = cls._normalizar(grupo.nome)
            if nome and (
                nome in texto or
                f'grupo regional {nome}' in texto or
                f'grupo {nome}' in texto or
                f'regional {nome}' in texto
            ):
                return grupo

        depois_de_grupo = re.search(r'\b(?:grupo(?:\s+regional)?|regional)\s+([a-z0-9\s-]{2,80})', texto)
        if depois_de_grupo:
            trecho = depois_de_grupo.group(1).strip()
            for grupo in GrupoRegional.objects.filter(ativo=True).order_by('nome'):
                if trecho and trecho in cls._normalizar(grupo.nome):
                    return grupo
        return None

    @classmethod
    def _validar_base_visivel(cls, user, base):
        if not base:
            return None
        return next((item for item in cls._bases_visiveis(user) if item.pk == base.pk), None)

    @classmethod
    def _validar_grupo_visivel(cls, user, grupo):
        if not grupo:
            return None
        return grupo if cls._bases_do_grupo_visiveis(user, grupo) else None

    @classmethod
    def _base_do_contexto(cls, user, contexto):
        nome = cls._normalizar(contexto.get('base', ''))
        if not nome:
            return None
        return next(
            (base for base in cls._bases_visiveis(user) if cls._normalizar(base.nome) == nome),
            None,
        )

    @classmethod
    def _grupo_do_contexto(cls, user, contexto):
        nome = cls._normalizar(contexto.get('grupo', ''))
        if not nome:
            return None
        grupo = next(
            (item for item in GrupoRegional.objects.filter(ativo=True) if cls._normalizar(item.nome) == nome),
            None,
        )
        return cls._validar_grupo_visivel(user, grupo)

    @classmethod
    def _extrair_cliente(cls, texto):
        from insumos.models import Cliente

        for alias, sigla in cls.CLIENTE_ALIASES.items():
            if re.search(rf'\b{re.escape(alias)}\b', texto):
                return Cliente.objects.filter(sigla__iexact=sigla).first()

        if cls._tem(
            texto, 'inventario', 'inventarios', 'loja', 'previsao', 'pecas',
            'produtividade', 'quantos', 'quantas', 'mes', 'semana', 'hoje', 'amanha',
            'gasto', 'gastos', 'custo', 'custos', 'despesa', 'despesas'
        ) or re.search(r'\b\d+\b', texto):
            scores_por_sigla = {}
            for alias, sigla in cls.CLIENTE_ALIASES.items():
                if ' ' in alias:
                    continue
                score = cls._melhor_similaridade_token(texto, alias)
                if score >= 0.82:
                    scores_por_sigla[sigla] = max(score, scores_por_sigla.get(sigla, 0))
            candidatos_alias = [(score, sigla) for sigla, score in scores_por_sigla.items()]
            candidatos_alias.sort(reverse=True)
            if candidatos_alias and (
                len(candidatos_alias) == 1 or
                candidatos_alias[0][0] - candidatos_alias[1][0] >= 0.05
            ):
                return Cliente.objects.filter(sigla__iexact=candidatos_alias[0][1]).first()

        # Clientes inativos permanecem consultáveis em inventários históricos.
        clientes = list(Cliente.objects.all().order_by('-nome'))
        for cliente in clientes:
            nome = cls._normalizar(cliente.nome)
            if nome and nome in texto:
                return cliente

        siglas_ignoradas = {'dia', 'pra', 'ate', 'sim', 'nao', 'mes', 'ano', 'por'}
        for cliente in clientes:
            sigla = cls._normalizar(cliente.sigla)
            codigo_loja = r'(?=[a-z0-9-]*\d)[a-z0-9-]+'
            if re.search(rf'\b{re.escape(sigla)}\b(?:\s+loja)?\s*{codigo_loja}\b', texto):
                return cliente
            if re.search(rf'\b(?:cliente|rede|do|da)\s+{re.escape(sigla)}\b', texto):
                return cliente
            if sigla in siglas_ignoradas:
                continue
            # Siglas de uma letra (como A) não podem competir com artigos da frase.
            if len(sigla) > 1 and re.search(rf'\b{re.escape(sigla)}\b', texto) and cls._tem(
                texto, 'inventario', 'inventarios', 'loja', 'previsao', 'pecas', 'produtividade',
                'cnpj', 'endereco', 'quantos', 'quantas', 'quantidade', 'total', 'mes',
                'semana', 'hoje', 'amanha', 'gasto', 'gastos', 'custo', 'custos',
                'despesa', 'despesas', 'fale', 'fala', 'sobre', 'resumo', 'visao',
            ):
                return cliente
        return None

    @staticmethod
    def _cliente_do_contexto(contexto):
        from insumos.models import Cliente

        sigla = contexto.get('cliente', '')
        return Cliente.objects.filter(sigla__iexact=sigla).first() if sigla else None

    @classmethod
    def _extrair_insumo(cls, texto):
        from insumos.models import Insumo

        ignorar = {
            'qual', 'quais', 'melhor', 'menor', 'maior', 'preco', 'precos',
            'comparar', 'compare', 'cotacao', 'cotacoes', 'fornecedor', 'fornecedores',
            'insumo', 'insumos', 'item', 'itens', 'valor', 'valores', 'online',
        }
        palavras = {
            palavra for palavra in re.findall(r'[a-z0-9]+', texto)
            if len(palavra) >= 3 and palavra not in ignorar
        }
        if not palavras:
            return None

        candidatos = []
        for insumo in Insumo.objects.filter(ativo=True).select_related('categoria'):
            descricao = cls._normalizar(insumo.descricao)
            tokens = set(re.findall(r'[a-z0-9]+', descricao))
            comuns = palavras & tokens
            if not comuns:
                continue
            score = len(comuns) * 2 + sum(len(token) for token in comuns) / 20
            if descricao in texto:
                score += 10
            candidatos.append((score, insumo))
        candidatos.sort(key=lambda item: (-item[0], item[1].descricao))
        if not candidatos:
            return None
        if len(candidatos) > 1 and candidatos[0][0] == candidatos[1][0]:
            return None
        return candidatos[0][1]

    @staticmethod
    def _insumo_do_contexto(contexto):
        from insumos.models import Insumo

        insumo_id = contexto.get('insumo_id')
        return Insumo.objects.filter(pk=insumo_id, ativo=True).first() if insumo_id else None

    @classmethod
    def _extrair_loja(cls, texto, cliente=None):
        match = re.search(r'\bloja\s+(?:n(?:umero)?\s*)?([a-z0-9-]+)\b', texto)
        if match and match.group(1) not in {'com', 'de', 'do', 'da', 'para', 'que'}:
            return match.group(1)
        if cliente:
            identificadores = {cls._normalizar(cliente.sigla), cls._normalizar(cliente.nome)}
            identificadores.update(
                alias for alias, sigla in cls.CLIENTE_ALIASES.items()
                if sigla.lower() == cliente.sigla.lower()
            )
            for identificador in sorted(identificadores, key=len, reverse=True):
                match = re.search(
                    rf'\b{re.escape(identificador)}\b\s*(?:loja\s*)?'
                    rf'((?=[a-z0-9-]*\d)[a-z0-9-]+)\b',
                    texto,
                )
                if match:
                    return match.group(1)
        return ''

    @staticmethod
    def _extrair_pessoas_filtro(texto):
        match = re.search(r'\b(?:com|para|de)\s+(\d+)\s+pessoas?\b', texto)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extrair_tipo_inventario(texto):
        tipos = {
            'oficial': 'T',
            'apoio': 'APOIO',
            'pre contagem': 'PRE',
            'contagem antecipada': 'CA',
            'controle de pallet': 'CP',
            'controle de pallets': 'CP',
            'divergencia': 'D',
        }
        for termo, codigo in tipos.items():
            if re.search(rf'\b{re.escape(termo)}\b', texto):
                return codigo
        if re.search(r'\b(?:inventario|tipo)\s+(?:oficial|total)\b', texto):
            return 'T'
        match = re.search(r'\btipo\s+(apoio|pre|ca|cp|im|lo|t|d|r|rc)\b', texto)
        return match.group(1).upper() if match else ''

    @staticmethod
    def _bases_visiveis(user):
        perfil = user.perfil
        if perfil.is_admin:
            bases = Base.objects.all().order_by('nome')
        else:
            bases = perfil.regionais.all().order_by('nome')
        return [base for base in bases if AssistenteOperacionalService._base_operacional(base)]

    @classmethod
    def _base_unica_visivel(cls, user):
        bases = cls._bases_visiveis(user)
        return bases[0] if len(bases) == 1 else None

    @classmethod
    def _opcoes_base_para_local_ambiguo(cls, user, texto):
        if re.search(r'\b(?:uf|estado)\s+(?:de\s+|do\s+|da\s+)?sao paulo\b', texto):
            return []
        if not re.search(r'\bsao paulo\b', texto):
            return []

        bases = cls._bases_visiveis(user)
        existe_base_exata = any(cls._normalizar(base.nome) == 'sao paulo' for base in bases)
        bases_sp = [base for base in bases if cls._base_pertence_uf(base, 'SP')]
        if not existe_base_exata or len(bases_sp) < 2:
            return []
        return sorted(bases_sp, key=lambda base: cls._normalizar(base.nome))

    @classmethod
    def _bases_da_uf_visiveis(cls, user, uf):
        return [base for base in cls._bases_visiveis(user) if cls._base_pertence_uf(base, uf)]

    @classmethod
    def _base_pertence_uf(cls, base, uf):
        nome = cls._normalizar(base.nome)
        padroes = {
            'SP': r'^(?:sp\b|sao paulo\b|oxxo sp\b)',
            'RJ': r'^(?:rj\b|rio de janeiro\b)',
            'PR': r'(?:^|/\s*)pr\b',
            'SC': r'(?:^|/\s*)sc\b|^joinville\b',
            'RS': r'^porto alegre\b|^rs\b',
        }
        padrao = padroes.get(uf, rf'^{re.escape(uf.lower())}\b')
        return bool(re.search(padrao, nome))

    @classmethod
    def _bases_do_escopo(cls, user, interpretacao):
        if interpretacao.base:
            return [interpretacao.base]
        if interpretacao.uf:
            return cls._bases_da_uf_visiveis(user, interpretacao.uf)
        if interpretacao.grupo:
            return cls._bases_do_grupo_visiveis(user, interpretacao.grupo)
        return cls._bases_visiveis(user)

    @staticmethod
    def _base_operacional(base):
        return AssistenteOperacionalService._normalizar(getattr(base, 'nome', '')) not in {'todas', 'todos'}

    @classmethod
    def _bases_do_grupo_visiveis(cls, user, grupo):
        bases_visiveis_ids = [base.pk for base in cls._bases_visiveis(user)]
        return list(
            Base.objects.filter(
                pk__in=bases_visiveis_ids,
                grupo_regional=grupo,
            ).order_by('nome')
        )

    @staticmethod
    def _extrair_data(texto):
        hoje = timezone.localdate()
        if re.search(r'\bhoje\b', texto):
            return hoje
        if re.search(r'\bamanha\b', texto):
            return hoje + timedelta(days=1)
        if re.search(r'\bontem\b', texto):
            return hoje - timedelta(days=1)

        iso = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', texto)
        if iso:
            return parse_date(iso.group(1))

        br = re.search(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b', texto)
        if br:
            dia, mes, ano = br.groups()
            ano = f'20{ano}' if len(ano) == 2 else ano
            return parse_date(f'{ano}-{int(mes):02d}-{int(dia):02d}')
        return None

    @classmethod
    def _extrair_periodo(cls, texto):
        data_exata = cls._extrair_data(texto)
        if data_exata:
            return data_exata, data_exata

        hoje = timezone.localdate()
        if re.search(r'\bsemana\b', texto):
            referencia = hoje + timedelta(days=7) if cls._tem(texto, 'proxima semana', 'semana que vem') else hoje
            inicio = referencia - timedelta(days=referencia.weekday())
            return inicio, inicio + timedelta(days=6)

        if re.search(r'\bmes\b', texto):
            if cls._tem(texto, 'proximo mes', 'mes que vem'):
                primeiro = (hoje.replace(day=28) + timedelta(days=4)).replace(day=1)
            else:
                primeiro = hoje.replace(day=1)
            proximo = (primeiro.replace(day=28) + timedelta(days=4)).replace(day=1)
            return primeiro, proximo - timedelta(days=1)

        if re.search(r'\bno dia\b', texto):
            return hoje, hoje
        return None, None

    @staticmethod
    def _normalizar(texto):
        texto = unicodedata.normalize('NFKD', (texto or '').lower())
        return ''.join(ch for ch in texto if not unicodedata.combining(ch))

    @staticmethod
    def _corrigir_termos(texto):
        termos = (
            'inventario', 'inventarios', 'equipamento', 'equipamentos',
            'coletor', 'coletores', 'impressora', 'impressoras', 'notebook',
            'notebooks', 'router', 'routers', 'transferencia', 'transferencias',
            'emprestimo', 'emprestimos', 'checklist', 'checklists', 'pessoas',
            'pessoa', 'loja', 'lojas', 'base', 'bases', 'insumo', 'insumos',
            'produtividade', 'previsao', 'pecas', 'apoio', 'historico',
            'endereco', 'lider', 'status', 'interior', 'leste', 'sul', 'litoral',
            'oxxo', 'gasto', 'gastos', 'custo', 'custos', 'custou', 'despesa',
            'despesas', 'financeiro', 'preco', 'precos', 'fornecedor',
            'fornecedores', 'confiabilidade',
            'cotacao', 'cotacoes', 'oferta', 'ofertas', 'pedido', 'pedidos',
            'solicitacao', 'solicitacoes', 'carrinho',
        )
        palavras = re.findall(r'\w+|\W+', texto, flags=re.UNICODE)
        corrigidas = []
        for palavra in palavras:
            if not palavra.isalnum() or palavra in termos or len(palavra) < 4:
                corrigidas.append(palavra)
                continue
            candidatos = [
                termo for termo in termos
                if termo[0] == palavra[0] and abs(len(termo) - len(palavra)) <= 2
            ]
            melhor = max(
                candidatos,
                key=lambda termo: SequenceMatcher(None, palavra, termo).ratio(),
                default='',
            )
            score = SequenceMatcher(None, palavra, melhor).ratio() if melhor else 0
            limite = 0.74 if len(palavra) <= 4 else 0.78 if len(palavra) <= 7 else 0.82
            if melhor and score >= limite:
                corrigidas.append(melhor)
            else:
                corrigidas.append(palavra)
        return ''.join(corrigidas)

    @staticmethod
    def _interpretar_linguagem_cotidiana(texto):
        texto = re.sub(r'\bosso\b', 'oxxo', texto)
        traducoes_es = {
            r'\bequipos?\b': 'equipamentos',
            r'\bcolectores?\b': 'coletores',
            r'\bimpresoras?\b': 'impressoras',
            r'\benrutadores?\b': 'roteadores',
            r'\bprestamos?\b': 'emprestimos',
            r'\bsuministros?\b': 'insumos',
            r'\bpersonas?\b': 'pessoas',
            r'\bhistorial(?:es)?\b': 'historico',
            r'\btransferencias?\b': 'transferencias',
        }
        for padrao, traducao in traducoes_es.items():
            texto = re.sub(padrao, traducao, texto)
        complementos = []

        if re.search(r'\b(maquininha|maquininhas|coletor de dados|leitor|leitores)\b', texto):
            complementos.append('coletores')
        elif re.search(r'\b(maquina|maquinas|aparelho|aparelhos|dispositivo|dispositivos)\b', texto):
            complementos.append('equipamentos')

        if re.search(r'\b(da conta|consegue|conseguem|aguenta|suporta|e suficiente|vai dar)\b', texto):
            complementos.append('atende')
        if re.search(r'\b(pessoal|time|turma|equipe)\b', texto):
            complementos.append('pessoas')

        equipamento_citado = bool(re.search(
            r'\b(equipamento|equipamentos|maquina|maquinas|maquininha|maquininhas|'
            r'aparelho|aparelhos|coletor|coletores|router|notebook|impressora)\b',
            texto,
        ))
        if equipamento_citado and re.search(
            r'\b(quebrou|quebrado|quebrada|defeito|defeituoso|parou|nao funciona|problema)\b',
            texto,
        ):
            complementos.extend(['sick', 'como marcar'])

        if equipamento_citado and re.search(
            r'\b(mandar|enviar|levar|mover|passar)\b.*\b(outra base|base destino|regional)\b',
            texto,
        ):
            complementos.extend(['transferencia', 'como fazer'])

        material_citado = bool(re.search(r'\b(material|materiais|insumo|insumos)\b', texto))
        if material_citado and re.search(
            r'\b(chegou|chegaram|recebi|recebemos|entrada|lancar|lanco|colocar no sistema)\b',
            texto,
        ):
            complementos.extend(['insumo', 'como cadastrar'])

        if re.search(r'\b(inventario|checklist)\b', texto) and re.search(
            r'\b(voltou|retornou|retorno|conferir|conferencia|informar devolucao|preencher)\b',
            texto,
        ):
            complementos.extend(['checklist', 'como preencher'])

        if re.search(r'\b(servico|servicos|trabalho|trabalhos|agenda)\b', texto) and re.search(
            r'\b(hoje|amanha|ontem)\b',
            texto,
        ):
            complementos.append('inventarios')

        return f"{texto} {' '.join(complementos)}".strip()

    @staticmethod
    def _tem(texto, *termos):
        return any(termo in texto for termo in termos)

    @staticmethod
    def _melhor_similaridade_token(texto, termo):
        termo = AssistenteOperacionalService._normalizar(termo)
        tokens = re.findall(r'[a-z0-9]+', AssistenteOperacionalService._normalizar(texto))
        return max(
            (SequenceMatcher(None, token, termo).ratio() for token in tokens),
            default=0,
        )

    @staticmethod
    def _quer_todas_bases(texto):
        if AssistenteOperacionalService._quer_todos_clientes(texto):
            return False
        padroes = (
            'cada uma delas',
            'cada uma',
            'todas elas',
            'todas as bases',
            'todas',
            'todos',
            'por base',
            'cada base',
        )
        return any(padrao in texto for padrao in padroes)

    @staticmethod
    def _quer_todos_clientes(texto):
        return any(
            padrao in texto
            for padrao in ('todos os clientes', 'todas as redes', 'qualquer cliente', 'sem filtrar cliente')
        )

    @staticmethod
    def _eh_saudacao(texto):
        texto = re.sub(r'[^a-z\s]', '', texto).strip()
        saudacoes = r'(?:oi|ola|bom dia|boa tarde|boa noite|e ai|e ae|eai|salve|hola|buenos dias|buenas tardes|buenas noches)'
        interacao = r'(?:tudo bem|ta tudo bem|como vai|como voce esta|como esta voce|todo bien|como estas|como esta)'
        return bool(re.fullmatch(rf'(?:{saudacoes})(?:\s+{interacao})?|{interacao}|ta ai', texto))

    @staticmethod
    def _remover_vocativo_tory(texto):
        texto = (texto or '').strip()
        tem_nome = bool(re.search(r'\btory\b', texto))
        texto = re.sub(r'^\s*tory\s*[,;:!?.-]*\s*', '', texto)
        texto = re.sub(r'\s*[,;:!?.-]*\s*tory\s*[,;:!?.-]*\s*$', '', texto)
        return texto.strip() or ('oi' if tem_nome else '')

    @staticmethod
    def _eh_continuacao(texto):
        return bool(
            re.search(
                r'^(e\b|entao\b|nessa\b|nesta\b|ela\b|isso\b|ainda\b|tambem\b|'
                r'a base\b|na base\b|base\b|essa base\b|esta base\b|a regional\b|essa regional\b|'
                r'da conta\b|consegue\b|tem\b|temos\b|possui\b|possuimos\b|ha\b|'
                r'e suficiente\b|vai dar\b)',
                texto,
            ) or
            re.search(r'\b(nao atende|atende mesmo|e suficiente|e isso)\b', texto)
        )

    @staticmethod
    def _eh_confirmacao_capacidade(texto):
        return bool(re.search(r'^(entao\b|isso\b)|\b(nao atende|atende mesmo)\b', texto))

    @staticmethod
    def _pergunta_capacidade_contextual(texto, contexto):
        pergunta_capacidade = bool(re.search(
            r'\b(atende|atendem|atender|suficiente|suficientes|da conta|consegue|'
            r'tem equipamento|tem equipamentos|temos equipamento|temos equipamentos)\b',
            texto,
        ))
        if not pergunta_capacidade:
            return False
        return bool(
            re.search(r'\b(equipamento|equipamentos|pessoas|pessoal|inventario|inventarios)\b', texto) or
            contexto.get('intencao') in {
                'inventarios_data_base',
                'capacidade_coletores',
                'capacidade_equipamentos',
            }
        )

    @staticmethod
    def _pergunta_relatorio_inventario(texto):
        return bool(re.search(
            r'\b(inventario|inventarios|previsao|pecas|produtividade|prod media|producao|'
            r'media|endereco|cnpj|cep|bairro|cidade|loja|lider|data|dia|quando|'
            r'pessoas|apoio|etapa|etapas|tipo|tipos|horario|historico|duracao|durou|demorou|'
            r'comecou|terminou|encerramento|atraso|atrasos|tempo produtivo|tempo efetivo|'
            r'custo adicional|ultrapassou|ultrapassar)\b',
            texto,
        ))

    @classmethod
    def _pergunta_planejamento(cls, texto, contexto):
        if cls._tem(texto, 'inventario local', 'inventarios locais', 'dados locais'):
            return False
        comparacao = bool(re.search(
            r'\b(planejado|planejamento|previsto)\b.*\b(realizado|execucao|real)\b|'
            r'\b(realizado|execucao|real)\b.*\b(planejado|planejamento|previsto)\b',
            texto,
        ))
        if not comparacao and cls._tem(
            texto,
            'terminou', 'terminaram', 'encerrado', 'encerrados', 'finalizado',
            'durou', 'inicio real', 'fim real', 'depois das', 'antes das',
            'tempo efetivo', 'tempo produtivo', 'custo adicional',
        ):
            return False

        explicit = bool(
            comparacao or
            re.search(r'\b(inventarios?|eventos?)\s+(?:ja\s+)?planejad', texto) or
            re.search(r'\b(equipe|pessoas|pecas)\s+previst', texto) or
            re.search(r'\bprevisao\b.*\bpecas\b|\bpecas\b.*\bprevisao\b', texto) or
            re.search(r'\bregional\s+responsavel\b', texto) or
            re.search(r'\beventos?\s+(?:pai|filho)\b|\b(?:pai|filho)\s+e\s+(?:pai|filho)\b', texto) or
            re.search(r'\bdisponibilidade\s+(?:da\s+)?equipe\b', texto) or
            re.search(r'\bavulsos?\b', texto)
        )
        future_period = bool(
            re.search(r'\b(inventario|inventarios|evento|eventos|agenda|servicos)\b', texto)
            and re.search(
                r'\b(amanha|proxima semana|semana que vem|nesta semana|esta semana|'
                r'no mes|neste mes|este mes|proximo mes|mes que vem)\b',
                texto,
            )
        )
        contextual = bool(
            contexto.get('intencao') == 'planejamento'
            and (
                cls._eh_continuacao(texto)
                or re.search(
                    r'\b(qual|quais|maior|menor|equipe|pessoas|pecas|regional|status|'
                    r'planejado|realizado|pai|filho|disponibilidade|avulso|detalhe)\b',
                    texto,
                )
            )
        )
        return explicit or future_period or contextual

    @staticmethod
    def _planning_action(texto, contexto):
        if re.search(r'\bavulsos?\b', texto) and re.search(r'\b(adicionar|adicionarmos|mais|incluir|incluirmos)\b', texto):
            return 'simulate_sporadic'
        if re.search(
            r'\b(planejado|planejamento|previsto)\b.*\b(realizado|execucao|real)\b|'
            r'\b(realizado|execucao|real)\b.*\b(planejado|planejamento|previsto)\b|'
            r'\bdiferenca\b.*\b(planejado|realizado)\b',
            texto,
        ):
            return 'comparison'
        if re.search(r'\bmaior\b.*\b(pecas|previsao|volume)\b', texto):
            return 'highest_pieces'
        if re.search(r'\bmaior\b.*\b(pessoas|equipe|demanda)\b', texto):
            return 'highest_headcount'
        if re.search(r'\b(?:somente|apenas)\s+(?:os\s+)?(?:eventos?\s+)?(?:pai|filhos?)\b', texto):
            return 'list'
        if re.search(r'\b(?:pai|filho)\b', texto):
            return 'hierarchy'
        if re.search(r'\b(disponibilidade|suficiente|suficientes|pessoas suficientes|equipe suficiente)\b', texto):
            return 'availability'
        if re.search(r'\b(equipe prevista|pessoas previstas|quantas pessoas|demanda de pessoas)\b', texto):
            return 'team'
        if contexto.get('intencao') == 'planejamento' and re.search(r'\btemos pessoas\b', texto):
            return 'availability'
        return 'list'

    @staticmethod
    def _extrair_status_planejamento(texto):
        mapping = {
            'cancelado': 'CANCELLED',
            'cancelados': 'CANCELLED',
            'modificado': 'MODIFIED',
            'modificados': 'MODIFIED',
            'adicionado': 'ADDED',
            'adicionados': 'ADDED',
            'removido': 'REMOVED',
            'removidos': 'REMOVED',
            'aprovado': 'APPROVED',
            'aprovados': 'APPROVED',
            'concluido': 'COMPLETED',
            'concluidos': 'COMPLETED',
            'em andamento': 'IN_PROGRESS',
            'pre planejado': 'PRE_PLANNED',
        }
        return list(dict.fromkeys(
            value for term, value in mapping.items()
            if re.search(rf'\b{re.escape(term)}\b', texto)
        ))

    @staticmethod
    def _extrair_kind_planejamento(texto):
        if re.search(r'\b(?:somente|apenas)\s+(?:os\s+)?(?:eventos?\s+)?pai\b', texto):
            return 'PAI'
        if re.search(r'\b(?:somente|apenas)\s+(?:os\s+)?(?:eventos?\s+)?filhos?\b', texto):
            return 'FILHO'
        return ''

    @staticmethod
    def _extrair_external_event_id(texto):
        match = re.search(r'\bevento\s+([a-z0-9][a-z0-9_-]{7,})\b', texto)
        return match.group(1) if match else ''

    @staticmethod
    def _extrair_local_planejamento(texto):
        for alias in sorted(AssistenteOperacionalService.BASE_ALIASES, key=len, reverse=True):
            if re.search(rf'\b{re.escape(alias)}\b', texto):
                return alias
        match = re.search(
            r'\b(?:na regional|na cidade de|em)\s+([a-z][a-z0-9\s-]{2,40})$',
            texto,
        )
        if not match:
            return ''
        location = re.sub(
            r'\s+\b(hoje|amanha|nesta semana|na proxima semana|neste mes)\b.*$',
            '',
            match.group(1),
        ).strip()
        if location in {'andamento', 'execucao', 'planejamento'}:
            return ''
        return location

    @staticmethod
    def _extrair_avulsos_simulados(texto):
        numbers = {
            'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'tres': 3,
            'quatro': 4, 'cinco': 5, 'seis': 6, 'sete': 7,
            'oito': 8, 'nove': 9, 'dez': 10,
        }
        match = re.search(
            r'\b(?:adicionar|adicionarmos|incluir|incluirmos|mais)\s+'
            r'(\d+|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez)\s+avulsos?\b',
            texto,
        )
        if not match:
            return None
        value = match.group(1)
        return int(value) if value.isdigit() else numbers[value]

    @staticmethod
    def _pergunta_tempos_operacionais(texto):
        return bool(re.search(
            r'\b(duracao|durou|demorou|tempo total|tempo efetivo|tempo produtivo|tempo improdutivo|'
            r'comecou|inicio real|inicio previsto|terminou|fim real|fim previsto|encerramento|'
            r'atraso|atrasos|depois das|antes das|mais \w+ pessoas|equipe necessaria|'
            r'acima da media|custo adicional|ultrapassou|ultrapassar)\b',
            texto,
        ))

    @staticmethod
    def _pergunta_ranking_atrasos(texto):
        return bool(
            re.search(r'\b(base|bases)\b', texto) and
            re.search(r'\b(atraso|atrasos|atrasam|atrasadas)\b', texto)
        )

    @staticmethod
    def _pergunta_simulacao_equipe(texto):
        return bool(
            re.search(r'\bmais\s+(?:\d+|uma|duas|tres|quatro|cinco|seis|sete|oito|nove|dez)\s+pessoas?\b', texto) or
            re.search(r'\b(?:fossem|com|equipe de)\s+\d+\s+pessoas?\b', texto)
        )

    @staticmethod
    def _extrair_adicional_equipe(texto):
        numeros = {
            'uma': 1, 'duas': 2, 'tres': 3, 'quatro': 4, 'cinco': 5,
            'seis': 6, 'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10,
        }
        match = re.search(
            r'\bmais\s+(\d+|uma|duas|tres|quatro|cinco|seis|sete|oito|nove|dez)\s+pessoas?\b',
            texto,
        )
        if not match:
            return None
        valor = match.group(1)
        return int(valor) if valor.isdigit() else numeros[valor]

    @staticmethod
    def _extrair_total_equipe_simulada(texto):
        match = re.search(r'\b(?:fossem|com|equipe de)\s+(\d+)\s+pessoas?\b', texto)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extrair_horario_inicio_hipotetico(texto):
        match = re.search(
            r'\b(?:comecado|comecasse|iniciado|iniciasse)\s+(?:as\s+)?(\d{1,2})(?::(\d{2}))?h?\b',
            texto,
        )
        return AssistenteOperacionalService._horario_do_match(match)

    @staticmethod
    def _extrair_horario_antes(texto):
        match = re.search(r'\bantes\s+d(?:as|e)\s+(\d{1,2})(?::(\d{2}))?h?\b', texto)
        return AssistenteOperacionalService._horario_do_match(match)

    @staticmethod
    def _extrair_horario_depois(texto):
        match = re.search(r'\bdepois\s+d(?:as|e)\s+(\d{1,2})(?::(\d{2}))?h?\b', texto)
        return AssistenteOperacionalService._horario_do_match(match)

    @staticmethod
    def _horario_do_match(match):
        if not match:
            return None
        hora = int(match.group(1))
        minuto = int(match.group(2) or 0)
        if hora > 23 or minuto > 59:
            return None
        return time(hour=hora, minute=minuto)

    @staticmethod
    def _pergunta_data_inventario(texto):
        return bool(re.search(
            r'\b(quando|que\s+(?:dia|data)|qual\s+(?:e\s+)?(?:o\s+)?(?:dia|data)|'
            r'(?:dia|data)\s+(?:do|da)\s+inventario)\b',
            texto,
        ))

    @staticmethod
    def _pergunta_testes_sistema(texto):
        return bool(re.search(
            r'\b(test\s*sist|teste(?:s)?\s+(?:de|do)\s+sistema|teste(?:s)?\s+sist)\b',
            texto,
        ))

    @staticmethod
    def _extrair_limite_ranking(texto, dimensao):
        numeros = {
            'uma': 1, 'duas': 2, 'tres': 3, 'quatro': 4, 'cinco': 5,
            'seis': 6, 'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10,
        }
        substantivos = {
            'base': r'bases?',
            'cliente': r'clientes?',
            'inventario': r'inventarios?',
        }
        match = re.search(
            rf'\b(\d+|uma|duas|tres|quatro|cinco|seis|sete|oito|nove|dez)\s+'
            rf'{substantivos[dimensao]}\b',
            texto,
        )
        if not match:
            return 10
        valor = match.group(1)
        limite = int(valor) if valor.isdigit() else numeros[valor]
        return min(max(limite, 1), 50)

    @classmethod
    def _analisar_ranking_custos(cls, texto):
        tem_ranking = bool(re.search(
            r'\b(maior|maiores|menor|menores|ranking|top)\b',
            texto,
        ))
        if re.search(r'\bpor\s+bases?\b', texto) or (
            tem_ranking and re.search(r'\bbases?\b', texto)
        ):
            dimensao = 'base'
        elif re.search(r'\bpor\s+clientes?\b', texto) or (
            tem_ranking and re.search(r'\bclientes\b', texto)
        ):
            dimensao = 'cliente'
        else:
            dimensao = 'inventario'
        return {
            'dimensao': dimensao,
            'maiores': not bool(re.search(r'\b(menor|menores)\b', texto)),
            'limite': cls._extrair_limite_ranking(texto, dimensao),
        }

    @staticmethod
    def _pergunta_custo_insumo(texto):
        termo_financeiro = re.search(
            r'\b(gasto|gastos|gastou|gastamos|custo|custos|custou|despesa|despesas|'
            r'valor gasto|quanto foi|quanto deu)\b',
            texto,
        )
        contexto_custo = re.search(
            r'\b(insumo|insumos|material|materiais|inventario|inventarios|cliente|loja|'
            r'mes|semana|periodo|tipo|pessoas)\b',
            texto,
        )
        ranking_ou_consulta_direta = re.search(
            r'\b(maior|maiores|menor|menores|ranking|top|total|qual|quais)\b',
            texto,
        )
        return bool(termo_financeiro and (contexto_custo or ranking_ou_consulta_direta))

    @staticmethod
    def _pergunta_comparacao_precos(texto):
        return bool(
            re.search(r'\b(preco|precos|cotacao|cotacoes|oferta|ofertas|fornecedor|fornecedores)\b', texto) and
            re.search(r'\b(comparar|compare|comparacao|melhor|menor|mais barato|valor|qual|quais)\b', texto)
        )

    @staticmethod
    def _pergunta_solicitacao_insumos(texto):
        return bool(
            re.search(r'\b(solicitacao|solicitacoes|pedido|pedidos)\b', texto) and
            re.search(r'\b(insumo|insumos|material|materiais|compras|meu|minha|meus|minhas)\b', texto)
        ) or bool(re.search(r'\bins-\d{6}-[a-z0-9]{6}\b', texto))

    @staticmethod
    def _pergunta_de_ajuda(texto):
        padroes = (
            'como faco', 'como fazer', 'como cadastrar', 'como cadastro',
            'como criar', 'como registrar', 'como marcar', 'como usar',
            'como receber', 'como devolver', 'como transferir', 'como solicitar',
            'como consultar', 'como editar', 'como excluir', 'como importar',
            'como preencher', 'como completar', 'como dar entrada',
            'onde faco', 'onde cadastrar', 'onde encontro', 'qual o procedimento',
            'onde lanco', 'onde informo', 'o que faco', 'o que devo fazer',
            'me ensina', 'me ajude a', 'como funciona',
        )
        return any(padrao in texto for padrao in padroes)

    @staticmethod
    def _pergunta_sobre_termo(texto):
        padroes = (
            'o que e', 'o que significa', 'qual o significado', 'significa o que',
            'qual a diferenca', 'qual diferenca', 'me explique', 'me explica',
            'para que serve', 'pra que serve', 'o que quer dizer',
        )
        return any(padrao in texto for padrao in padroes)

    @staticmethod
    def _extrair_protocolo(texto):
        texto = (texto or '').upper()
        match = re.search(r'\b(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+){1,3}\b', texto)
        if not match:
            match = re.search(r'\b(?=[A-Z0-9]*\d)[A-Z0-9]{6,20}\b', texto)
        return match.group(0) if match else ''

    @staticmethod
    def _formatar_grupo(itens, campo):
        return '; '.join(f"{item.get(campo) or '-'}: {item['total']}" for item in itens)

    @staticmethod
    def _formatar_periodo_grupo(grupo):
        inicio = grupo['data_inicio']
        fim = grupo['data_fim']
        if inicio == fim:
            return f'{inicio:%d/%m/%Y}'
        return f'{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}'

    @staticmethod
    def _valor_grupo(grupo, campo):
        candidatos = [grupo['representante'], *reversed(grupo['itens'])]
        vistos = set()
        for item in candidatos:
            if item.pk in vistos:
                continue
            vistos.add(item.pk)
            valor = getattr(item, campo, None)
            if valor is None:
                continue
            texto = str(valor).strip()
            if texto and texto.upper() not in {'NA', 'N/A', 'NÃO', 'NAO', '-'}:
                return texto
        return '-'

    @classmethod
    def _dado_bruto(cls, inventario, nome):
        nome_normalizado = cls._normalizar(nome)
        for chave, valor in (inventario.dados_brutos or {}).items():
            if cls._normalizar(chave) == nome_normalizado:
                return valor
        return ''

    @classmethod
    def _agrupar_inventarios_logicos(cls, inventarios):
        buckets = defaultdict(list)
        for inv in inventarios:
            # APOIO pode vir de outra base, mas continua pertencendo ao ciclo da mesma loja.
            buckets[(inv.cliente_id, str(inv.loja).strip().lower())].append(inv)

        grupos = []
        for bucket in buckets.values():
            ordenados = sorted(bucket, key=lambda item: (item.data_inicio, item.pk))
            independentes = [inv for inv in ordenados if (inv.tipo or '').strip().upper() in {'IM', 'LO'}]
            operacionais = [inv for inv in ordenados if inv not in independentes]
            for inv in independentes:
                grupos.append(cls._montar_grupo_inventario([inv], inv))

            pais = [inv for inv in operacionais if (inv.tipo or '').strip().upper() == 'T']
            if not pais:
                if operacionais:
                    grupos.append(cls._montar_grupo_inventario(operacionais, None))
                continue

            itens_por_pai = {pai.pk: [pai] for pai in pais}
            for inv in operacionais:
                if inv.pk in itens_por_pai:
                    continue
                pai = cls._pai_mais_proximo(inv, pais)
                itens_por_pai[pai.pk].append(inv)
            for pai in pais:
                grupos.append(cls._montar_grupo_inventario(itens_por_pai[pai.pk], pai))

        return sorted(
            grupos,
            key=lambda grupo: (
                grupo['data_inicio'],
                grupo['representante'].cliente.sigla,
                str(grupo['representante'].loja),
            ),
        )

    @staticmethod
    def _pai_mais_proximo(inventario, pais):
        tipo = (inventario.tipo or '').strip().upper()
        anteriores = [pai for pai in pais if pai.data_inicio <= inventario.data_inicio]
        posteriores = [pai for pai in pais if pai.data_inicio >= inventario.data_inicio]
        anterior = max(anteriores, key=lambda pai: (pai.data_inicio, pai.pk), default=None)
        posterior = min(posteriores, key=lambda pai: (pai.data_inicio, pai.pk), default=None)
        if anterior is None:
            return posterior
        if posterior is None:
            return anterior
        distancia_anterior = (inventario.data_inicio - anterior.data_inicio).days
        distancia_posterior = (posterior.data_inicio - inventario.data_inicio).days
        if distancia_anterior < distancia_posterior:
            return anterior
        if distancia_posterior < distancia_anterior:
            return posterior
        # Divergências e recontagens fecham o ciclo anterior; preparações abrem o próximo.
        return anterior if tipo in {'D', 'R', 'RC'} else posterior

    @classmethod
    def _montar_grupo_inventario(cls, itens, pai):
        representante = pai or max(itens, key=lambda item: (item.data_inicio, item.pk))
        tipos = []
        for item in itens:
            tipo = (item.tipo or '-').strip().upper() or '-'
            if tipo not in tipos:
                tipos.append(tipo)
        pessoas_por_tipo = defaultdict(int)
        bases = []
        for item in itens:
            tipo = (item.tipo or '-').strip().upper() or '-'
            pessoas_por_tipo[tipo] += cls._pessoas_inventario(item)
            if item.base not in bases:
                bases.append(item.base)
        return {
            'representante': representante,
            'pai': pai,
            'itens': itens,
            'tipos': tipos,
            'bases': bases,
            'pessoas_por_tipo': dict(pessoas_por_tipo),
            'data_inicio': min(item.data_inicio for item in itens),
            'data_fim': max(item.data_inicio for item in itens),
            'pessoas': sum(cls._pessoas_inventario(item) for item in itens),
            'pessoas_oficial_apoio': pessoas_por_tipo.get('T', 0) + pessoas_por_tipo.get('APOIO', 0),
            'previsao': representante.previsao_pecas,
            'prod_media': representante.prod_media,
            'status': representante.status,
        }

    @classmethod
    def _estimar_grupos_inventario(cls, user, grupos):
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        resultado = {
            grupo['representante'].pk: {
                'previsao': None,
                'previsao_amostras': 0,
                'prod_media': None,
                'prod_amostras': 0,
            }
            for grupo in grupos
        }
        clientes_ids = {grupo['representante'].cliente_id for grupo in grupos}
        if not clientes_ids:
            return resultado

        comparaveis_qs = secure_queryset_insumos(
            Inventario.objects.select_related('cliente', 'base').filter(
                base__in=cls._bases_visiveis(user),
                cliente_id__in=clientes_ids,
            ),
            user,
            campo_base='base',
        )
        comparaveis = cls._agrupar_inventarios_logicos(list(comparaveis_qs))
        mapas_previsao = [defaultdict(list), defaultdict(list), defaultdict(list)]
        mapas_prod = [defaultdict(list), defaultdict(list), defaultdict(list)]
        for grupo in comparaveis:
            inv = grupo['representante']
            equipe_contagem = cls._equipe_produtiva_grupo(grupo)
            chaves = (
                (inv.cliente_id, str(inv.loja).strip().lower()),
                (inv.cliente_id, equipe_contagem),
                inv.cliente_id,
            )
            if grupo['previsao'] is not None and equipe_contagem:
                razao = grupo['previsao'] / equipe_contagem
                for mapa, chave in zip(mapas_previsao, chaves):
                    mapa[chave].append(razao)
            if grupo['prod_media'] is not None:
                for mapa, chave in zip(mapas_prod, chaves):
                    mapa[chave].append(grupo['prod_media'])

        for grupo in grupos:
            inv = grupo['representante']
            equipe_contagem = cls._equipe_produtiva_grupo(grupo)
            chaves = (
                (inv.cliente_id, str(inv.loja).strip().lower()),
                (inv.cliente_id, equipe_contagem),
                inv.cliente_id,
            )
            estimativa = resultado[inv.pk]
            if grupo['previsao'] is None and equipe_contagem and 'LO' not in grupo['tipos']:
                for mapa, chave in zip(mapas_previsao, chaves):
                    amostras = mapa.get(chave, [])
                    if amostras:
                        estimativa['previsao'] = round(sum(amostras) / len(amostras) * equipe_contagem)
                        estimativa['previsao_amostras'] = len(amostras)
                        break
            if grupo['prod_media'] is None and 'LO' not in grupo['tipos']:
                for mapa, chave in zip(mapas_prod, chaves):
                    amostras = mapa.get(chave, [])
                    if amostras:
                        estimativa['prod_media'] = sum(amostras) / len(amostras)
                        estimativa['prod_amostras'] = len(amostras)
                        break
        return resultado

    @classmethod
    def _estimar_dados_inventarios(cls, user, inventarios):
        from insumos.models import Inventario
        from insumos.utils import secure_queryset_insumos

        resultado = {
            inv.pk: {
                'previsao': None,
                'previsao_amostras': 0,
                'prod_media': None,
                'prod_amostras': 0,
            }
            for inv in inventarios
        }
        clientes_ids = {inv.cliente_id for inv in inventarios}
        if not clientes_ids:
            return resultado

        comparaveis = secure_queryset_insumos(
            Inventario.objects.filter(
                base__in=cls._bases_visiveis(user),
                cliente_id__in=clientes_ids,
            ),
            user,
            campo_base='base',
        ).values('cliente_id', 'loja', 'pessoas', 'previsao_pecas', 'prod_media')

        mapas_previsao = [defaultdict(list), defaultdict(list), defaultdict(list)]
        mapas_prod = [defaultdict(list), defaultdict(list), defaultdict(list)]
        for item in comparaveis:
            cliente_id = item['cliente_id']
            loja = str(item['loja']).strip().lower()
            pessoas = item['pessoas']
            chaves = ((cliente_id, loja), (cliente_id, pessoas), cliente_id)
            if item['previsao_pecas'] is not None and pessoas:
                razao = item['previsao_pecas'] / pessoas
                for mapa, chave in zip(mapas_previsao, chaves):
                    mapa[chave].append(razao)
            if item['prod_media'] is not None:
                for mapa, chave in zip(mapas_prod, chaves):
                    mapa[chave].append(item['prod_media'])

        for inv in inventarios:
            chaves = (
                (inv.cliente_id, str(inv.loja).strip().lower()),
                (inv.cliente_id, inv.pessoas),
                inv.cliente_id,
            )
            if inv.previsao_pecas is None and inv.pessoas:
                for mapa, chave in zip(mapas_previsao, chaves):
                    amostras = mapa.get(chave, [])
                    if amostras:
                        resultado[inv.pk]['previsao'] = round(sum(amostras) / len(amostras) * inv.pessoas)
                        resultado[inv.pk]['previsao_amostras'] = len(amostras)
                        break
            if inv.prod_media is None:
                for mapa, chave in zip(mapas_prod, chaves):
                    amostras = mapa.get(chave, [])
                    if amostras:
                        resultado[inv.pk]['prod_media'] = sum(amostras) / len(amostras)
                        resultado[inv.pk]['prod_amostras'] = len(amostras)
                        break
        return resultado

    @classmethod
    def _descricao_filtro_inventario(cls, interpretacao):
        partes = []
        if interpretacao.cliente:
            partes.append(f'{interpretacao.cliente.nome} ({interpretacao.cliente.sigla})')
        if interpretacao.loja:
            partes.append(f'loja {interpretacao.loja}')
        if interpretacao.base:
            partes.append(f'base {interpretacao.base.nome}')
        elif interpretacao.uf:
            partes.append(f'UF {interpretacao.uf}')
        elif interpretacao.grupo:
            partes.append(f'grupo {interpretacao.grupo.nome}')
        if interpretacao.pessoas_filtro is not None:
            partes.append(f'{interpretacao.pessoas_filtro} pessoas')
        if interpretacao.periodo_inicio and interpretacao.periodo_fim:
            if interpretacao.periodo_inicio == interpretacao.periodo_fim:
                partes.append(f'{interpretacao.periodo_inicio:%d/%m/%Y}')
            else:
                partes.append(
                    f'{interpretacao.periodo_inicio:%d/%m/%Y} a {interpretacao.periodo_fim:%d/%m/%Y}'
                )
        return ' - '.join(partes) if partes else 'o seu escopo permitido'

    @staticmethod
    def _descricao_escopo_geografico(interpretacao, prefixo=''):
        if interpretacao.base:
            return f'{prefixo} {interpretacao.base.nome}'
        if interpretacao.uf:
            return f'{prefixo} UF {interpretacao.uf}'
        if interpretacao.grupo:
            return f'{prefixo} grupo {interpretacao.grupo.nome}'
        return ''

    @staticmethod
    def _formatar_numero(valor):
        if valor is None:
            return '-'
        numero = float(valor)
        if numero.is_integer():
            return f'{int(numero):,}'.replace(',', '.')
        return f'{numero:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

    @staticmethod
    def _formatar_decimal(valor):
        if valor is None:
            return '-'
        return f'{float(valor):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

    @staticmethod
    def _formatar_horario(valor):
        return f'{valor:%H:%M}' if valor else '-'

    @staticmethod
    def _datetime_local(valor):
        if valor is None:
            return None
        return timezone.localtime(valor) if timezone.is_aware(valor) else valor

    @classmethod
    def _formatar_datetime(cls, valor):
        valor = cls._datetime_local(valor)
        return f'{valor:%d/%m/%Y às %H:%M}' if valor else '-'

    @staticmethod
    def _formatar_horas(valor):
        if valor is None:
            return '-'
        minutos = round(abs(float(valor)) * 60)
        horas, minutos = divmod(minutos, 60)
        sinal = '-' if valor < 0 else ''
        return f'{sinal}{horas}h{minutos:02d}'

    @staticmethod
    def _formatar_minutos(valor):
        if valor is None:
            return '-'
        minutos = round(abs(float(valor)))
        horas, minutos = divmod(minutos, 60)
        if horas:
            return f'{horas}h{minutos:02d}'
        return f'{minutos} min'

    @staticmethod
    def _formatar_percentual(valor):
        if valor in (None, ''):
            return '-'
        try:
            numero = float(str(valor).replace(',', '.'))
        except (TypeError, ValueError):
            return str(valor)
        if 0 <= numero <= 1:
            numero *= 100
        return f'{numero:.0f}%'

    @classmethod
    def _pessoas_inventario(cls, inventario):
        if inventario.pessoas is not None:
            return inventario.pessoas or 0

        dados = inventario.dados_brutos or {}
        valor = (
            dados.get('PESSOAS') or
            dados.get('Pessoas') or
            dados.get('pessoas') or
            dados.get('QTDE PESSOAS') or
            dados.get('QTD_PESSOAS')
        )
        return cls._inteiro_seguro(valor)

    @staticmethod
    def _inteiro_seguro(valor):
        if valor in (None, ''):
            return 0
        if isinstance(valor, Number):
            return int(valor)
        texto = str(valor).strip()
        match = re.search(r'\d+', texto)
        return int(match.group(0)) if match else 0

    @staticmethod
    def _resumo_interpretacao(interpretacao):
        partes = [f'intencao={interpretacao.intencao}']
        if interpretacao.categoria:
            partes.append(f'categoria={interpretacao.categoria}')
        if interpretacao.base:
            partes.append(f'base={interpretacao.base.nome}')
        if interpretacao.grupo:
            partes.append(f'grupo={interpretacao.grupo.nome}')
        if interpretacao.uf:
            partes.append(f'uf={interpretacao.uf}')
        if interpretacao.base_bloqueada:
            partes.append(f'base_sem_acesso={interpretacao.base_bloqueada}')
        if interpretacao.grupo_bloqueado:
            partes.append(f'grupo_sem_acesso={interpretacao.grupo_bloqueado}')
        if interpretacao.uf_bloqueada:
            partes.append(f'uf_sem_acesso={interpretacao.uf_bloqueada}')
        if interpretacao.opcoes_base:
            partes.append(f'bases_disponiveis={len(interpretacao.opcoes_base)}')
        if interpretacao.todas_bases:
            partes.append('todas_bases=True')
        if interpretacao.status:
            partes.append(f'status={interpretacao.status}')
        if interpretacao.data:
            partes.append(f'data={interpretacao.data:%d/%m/%Y}')
        if interpretacao.protocolo:
            partes.append(f'protocolo={interpretacao.protocolo}')
        if interpretacao.cliente:
            partes.append(f'cliente={interpretacao.cliente.sigla}')
        if interpretacao.loja:
            partes.append(f'loja={interpretacao.loja}')
        if interpretacao.pessoas_filtro is not None:
            partes.append(f'pessoas={interpretacao.pessoas_filtro}')
        if interpretacao.tipo_inventario:
            partes.append(f'tipo={interpretacao.tipo_inventario}')
        if interpretacao.insumo:
            partes.append(f'insumo={interpretacao.insumo.descricao}')
        if interpretacao.periodo_inicio and interpretacao.periodo_fim:
            partes.append(f'periodo={interpretacao.periodo_inicio:%d/%m/%Y}..{interpretacao.periodo_fim:%d/%m/%Y}')
        if interpretacao.external_event_id:
            partes.append(f'external_event_id={interpretacao.external_event_id}')
        if interpretacao.external_region_name:
            partes.append(f'regional_externa={interpretacao.external_region_name}')
        if interpretacao.external_client_name:
            partes.append(f'cliente_externo={interpretacao.external_client_name}')
        if interpretacao.external_store_name:
            partes.append(f'loja_externa={interpretacao.external_store_name}')
        if interpretacao.external_inventory_type_name:
            partes.append(f'tipo_externo={interpretacao.external_inventory_type_name}')
        return ', '.join(partes)

    @staticmethod
    def _contexto_interpretacao(interpretacao):
        intencao = interpretacao.intencao
        if intencao == 'escolher_base':
            if (
                ('pessoas' in interpretacao.texto or 'atende' in interpretacao.texto or 'atendem' in interpretacao.texto) and
                (interpretacao.categoria == 'Coletores' or 'coletor' in interpretacao.texto or 'coletores' in interpretacao.texto)
            ):
                intencao = 'capacidade_coletores'
            elif (
                ('equipamento' in interpretacao.texto or 'equipamentos' in interpretacao.texto) and
                re.search(
                    r'\b(atende|atendem|atender|suficiente|tem|temos|possui|possuimos|da conta)\b',
                    interpretacao.texto,
                )
            ):
                intencao = 'capacidade_equipamentos'
            elif (
                ('inventario' in interpretacao.texto or 'inventarios' in interpretacao.texto) and
                ('equipamento' in interpretacao.texto or 'equipamentos' in interpretacao.texto)
            ):
                intencao = 'capacidade_equipamentos'
            elif 'inventario' in interpretacao.texto or 'inventarios' in interpretacao.texto:
                intencao = 'inventarios_data_base'
            elif interpretacao.categoria:
                intencao = 'equipamentos_categoria'

        return {
            'intencao': intencao,
            'categoria': interpretacao.categoria,
            'status': interpretacao.status if intencao == 'equipamentos_categoria' else '',
            'base': interpretacao.base.nome if interpretacao.base else '',
            'grupo': interpretacao.grupo.nome if interpretacao.grupo else '',
            'uf': interpretacao.uf,
            'todas_bases': interpretacao.todas_bases,
            'data': interpretacao.data.isoformat() if interpretacao.data else '',
            'cliente': interpretacao.cliente.sigla if interpretacao.cliente else '',
            'loja': interpretacao.loja,
            'pessoas_filtro': interpretacao.pessoas_filtro,
            'tipo_inventario': interpretacao.tipo_inventario,
            'insumo_id': interpretacao.insumo.id if interpretacao.insumo else None,
            'periodo_inicio': interpretacao.periodo_inicio.isoformat() if interpretacao.periodo_inicio else '',
            'periodo_fim': interpretacao.periodo_fim.isoformat() if interpretacao.periodo_fim else '',
            'planning_action': interpretacao.planning_action,
            'planning_statuses': interpretacao.planning_statuses,
            'planning_location': interpretacao.planning_location,
            'external_event_id': interpretacao.external_event_id,
            'external_client_id': interpretacao.external_client_id,
            'external_client_name': interpretacao.external_client_name,
            'external_store_id': interpretacao.external_store_id,
            'external_store_name': interpretacao.external_store_name,
            'external_region_id': interpretacao.external_region_id,
            'external_region_name': interpretacao.external_region_name,
            'external_inventory_type_name': interpretacao.external_inventory_type_name,
            'external_inventory_type_kind': interpretacao.external_inventory_type_kind,
        }

    @staticmethod
    def _acoes_interpretacao(interpretacao):
        if interpretacao.intencao != 'escolher_base':
            return []
        opcoes = list(interpretacao.opcoes_base)
        acoes = [
            {
                'label': nome,
                'pergunta': f'Na base {nome}',
            }
            for nome in opcoes
        ]
        if re.search(r'\bsao paulo\b', interpretacao.texto):
            acoes.sort(
                key=lambda item: (
                    AssistenteOperacionalService._normalizar(item['label']) != 'sao paulo',
                    AssistenteOperacionalService._normalizar(item['label']),
                )
            )
            acao_estado = {
                'label': 'Todo o estado de SP',
                'pergunta': 'UF SP',
            }
            if len(acoes) > 10:
                exata = [
                    item for item in acoes
                    if AssistenteOperacionalService._normalizar(item['label']) == 'sao paulo'
                ]
                return exata + [acao_estado]
            acoes.insert(1 if acoes else 0, acao_estado)
        return acoes

    @staticmethod
    def _data_contexto(contexto):
        valor = contexto.get('data')
        return parse_date(valor) if valor else None

    @staticmethod
    def _data_contexto_chave(contexto, chave):
        valor = contexto.get(chave)
        return parse_date(valor) if valor else None

    @classmethod
    def _personalizar_resposta(cls, user, texto, *, pergunta='', intencao=''):
        nome = cls._nome_usuario(user)
        if not texto:
            return 'Não consegui formar uma resposta segura para essa pergunta agora.'
        if intencao == 'saudacao':
            return texto
        pergunta_normalizada = cls._normalizar(pergunta)
        if re.search(r'\btory\b', pergunta_normalizada):
            return f'Claro, {nome}. {texto[:1].lower()}{texto[1:]}'
        # Mantém o texto factual do serviço e evita repetir o nome do usuário
        # mecanicamente em todas as respostas.
        return f'{texto[:1].lower()}{texto[1:]}'

    @staticmethod
    def _nome_usuario(user):
        nome_completo = (user.get_full_name() or '').strip()
        if nome_completo:
            return nome_completo.split()[0]
        primeiro_nome = (getattr(user, 'first_name', '') or '').strip()
        if primeiro_nome:
            return primeiro_nome.split()[0]
        return user.get_username()

    @staticmethod
    def _resposta(categoria, resposta):
        return {
            'categoria': categoria,
            'resposta': resposta,
        }
