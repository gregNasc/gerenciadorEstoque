import json
import logging
from dataclasses import dataclass, field
from datetime import date

import httpx
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date


logger = logging.getLogger("integracao.tory_llm")


@dataclass(frozen=True)
class PortalQuestionPlan:
    intent: str = ""
    confidence: float = 0.0
    is_follow_up: bool = False
    is_portal_query: bool = False
    status: str = "any"
    client_code: str = ""
    store_number: str = ""
    start_date: date | None = None
    end_date: date | None = None
    metrics: list[str] = field(default_factory=list)


class PortalQuestionInterpreter:
    """Transforma linguagem natural em intenção e filtros estritamente validados."""

    ALLOWED_INTENTS = {
        "saudacao", "ajuda_sistema", "glossario", "portal_tempo_real",
        "planejamento", "ranking_base", "capacidade_coletores",
        "capacidade_equipamentos", "inventarios_data_base",
        "inventarios_relatorio", "custos_insumos", "comparacao_precos",
        "solicitacoes_insumos", "testes_sistema", "equipamentos_categoria",
        "equipamentos", "insumos", "transferencias", "historico",
        "inventarios_checklists", "indicadores", "orientacao",
    }

    ALLOWED_STATUS = {"any", "in_progress", "finalized", "scheduled", "preparation"}
    ALLOWED_METRICS = {
        "summary",
        "all",
        "total_items",
        "total_products",
        "productivity",
        "divergences",
        "accuracy",
        "progress",
        "sections",
        "conferents",
        "times",
        "address",
        "connection",
        "indicators",
        "counts",
    }
    SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {
                "type": "string",
                "enum": sorted(ALLOWED_INTENTS),
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "is_follow_up": {"type": "boolean"},
            "is_portal_query": {"type": "boolean"},
            "status": {
                "type": "string",
                "enum": ["any", "in_progress", "finalized", "scheduled", "preparation"],
            },
            "client_code": {"type": "string"},
            "store_number": {"type": "string"},
            "start_date": {"type": ["string", "null"]},
            "end_date": {"type": ["string", "null"]},
            "metrics": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "summary", "all", "total_items", "total_products",
                        "productivity", "divergences", "accuracy", "progress",
                        "sections", "conferents", "times", "address", "connection",
                        "indicators", "counts",
                    ],
                },
            },
        },
        "required": [
            "intent", "confidence", "is_follow_up",
            "is_portal_query", "status", "client_code", "store_number",
            "start_date", "end_date", "metrics",
        ],
    }

    @classmethod
    def interpret(cls, question, *, context=None, today=None, http_client=None):
        if not settings.TORY_LLM_ENABLED or not settings.OPENAI_API_KEY:
            return None
        today = today or timezone.localdate()
        context = context or {}
        client = http_client or httpx.Client(
            timeout=httpx.Timeout(settings.TORY_LLM_TIMEOUT),
            follow_redirects=False,
            verify=True,
        )
        owns_client = http_client is None
        try:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.TORY_LLM_MODEL,
                    "store": False,
                    "reasoning": {"effort": settings.TORY_LLM_REASONING_EFFORT},
                    "max_output_tokens": 900,
                    "input": [
                        {
                            "role": "developer",
                            "content": cls._instructions(today),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "question": str(question or "")[:2000],
                                    "previous_context": cls._safe_context(context),
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "tory_question_intent",
                            "strict": True,
                            "schema": cls.SCHEMA,
                        }
                    },
                },
            )
            response.raise_for_status()
            return cls._validate(json.loads(cls._output_text(response.json())))
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            logger.exception("tory_llm_interpretation_failed")
            return None
        finally:
            if owns_client:
                client.close()

    @staticmethod
    def _instructions(today):
        return f"""
Você é o interpretador semântico da Tory, assistente do sistema de operações,
estoque e inventários da Inventory Brasil.
Hoje é {today.isoformat()} no fuso America/Sao_Paulo.
Retorne somente o objeto do schema. Não responda à pergunta e não invente valores.

Classifique a intenção principal considerando a pergunta inteira e
previous_context. Use is_follow_up=true somente quando a pergunta depender do
assunto ou dos filtros anteriores. Confiança deve refletir a clareza real do
pedido; em dúvida, use intent=orientacao e confiança baixa.

Intenções disponíveis:
- saudacao: cumprimento sem pedido operacional;
- ajuda_sistema ou glossario: como usar o sistema ou significado de um termo;
- planejamento: agenda futura, previsão, equipe/peças planejadas e eventos;
- portal_tempo_real: execução em andamento ou finalizada lida no Portal;
- inventarios_data_base: inventários locais por data/base, sem análise extensa;
- inventarios_relatorio: dados registrados de execução, produtividade, tempos,
  cliente, loja, equipe, endereço, custos operacionais ou histórico do inventário;
- capacidade_coletores/capacidade_equipamentos: se os recursos atendem a demanda;
- ranking_base: comparação, maior/menor ou ranking entre bases;
- equipamentos_categoria/equipamentos: quantidade/listagem por tipo ou detalhes
  patrimoniais, status, finalidade, SICK, empréstimos e vínculos;
- insumos, custos_insumos, comparacao_precos ou solicitacoes_insumos: estoque de
  materiais, consumo/custo, fornecedores/cotações ou solicitações;
- transferencias ou historico: transferências/protocolos ou movimentações de
  equipamento;
- inventarios_checklists: checklist/devolução de inventário;
- testes_sistema: testes, alertas e saúde operacional registrados;
- indicadores: visão geral/KPIs; orientacao: pedido sem domínio identificável.

Considere consulta do Portal quando o usuário pedir inventários em andamento,
agora/neste momento, finalizados, progresso, total de peças ou itens contados,
produtividade, divergências, acuracidade, seções, conferentes, conexão, indicadores,
contagens ou mencionar explicitamente Portal/tempo real. Uma continuação usa
previous_context.
Se o usuário pedir explicitamente dados locais, relatório local ou planejamento,
marque is_portal_query=false mesmo quando previous_context for do Portal.

Mapeamentos:
- agora, neste/nesse momento, rolando: status=in_progress e data de hoje;
- em andamento: status=in_progress;
- finalizado/concluído/encerrado: status=finalized;
- peça/item contado: total_items; SKU/produto contado: total_products;
- indicadores/KPIs: indicators; contagem/contagens/recontagens: counts;
- maior/pior diferença ou erro de contagem: divergences;
- "todas as informações" ou equivalente: all.

Datas devem ser ISO YYYY-MM-DD. Use null quando não houver data. Não transforme
número de loja em client_code. Não copie campos desconhecidos do contexto.
is_portal_query deve ser true exatamente quando intent=portal_tempo_real.
""".strip()

    @staticmethod
    def _safe_context(context):
        return {
            "intent": context.get("intencao", ""),
            "client_code": context.get("portal_client_code") or context.get("cliente", ""),
            "store_number": context.get("loja", ""),
            "start_date": context.get("periodo_inicio", ""),
            "end_date": context.get("periodo_fim", ""),
            "status": context.get("portal_status", "any"),
            "metrics": context.get("portal_metrics", []),
        }

    @staticmethod
    def _output_text(payload):
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
        raise ValueError("Resposta do LLM sem output_text.")

    @classmethod
    def _validate(cls, payload):
        status = payload.get("status", "any")
        if status not in cls.ALLOWED_STATUS:
            status = "any"
        metrics = [
            metric for metric in payload.get("metrics", [])
            if metric in cls.ALLOWED_METRICS
        ]
        start = parse_date(payload.get("start_date") or "")
        end = parse_date(payload.get("end_date") or "")
        if start and not end:
            end = start
        if end and not start:
            start = end
        if start and end and end < start:
            start, end = end, start
        intent = (
            payload.get("intent", "")
            if payload.get("intent", "") in cls.ALLOWED_INTENTS
            else ""
        )
        return PortalQuestionPlan(
            intent=intent,
            confidence=max(0.0, min(1.0, cls._confidence(payload.get("confidence")))),
            is_follow_up=bool(payload.get("is_follow_up")),
            is_portal_query=(
                intent == "portal_tempo_real"
                if intent
                else bool(payload.get("is_portal_query"))
            ),
            status=status,
            client_code=str(payload.get("client_code") or "").strip().upper()[:20],
            store_number=str(payload.get("store_number") or "").strip()[:50],
            start_date=start,
            end_date=end,
            metrics=list(dict.fromkeys(metrics)) or ["summary"],
        )

    @staticmethod
    def _confidence(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
