import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils import timezone

from integracao.clients.inventory_portal import InventoryPortalClient
from integracao.exceptions import (
    InventoryPortalAuthenticationError,
    InventoryPortalConfigurationError,
    InventoryPortalError,
)
from insumos.models import Inventario
from insumos.utils import secure_queryset_insumos


class InventoryPortalAssistantService:
    """Expõe à Tory somente leituras autorizadas do Portal Inventory Brasil."""

    FIELD_LABELS = {
        "scheduledDate": "Data do inventário",
        "statusId": "Status",
        "qtyPeople": "Quantidade de pessoas",
        "liderNameBME": "Líder",
        "nameResponsibleCustomer": "Responsável do cliente",
        "realtime_alteracao": "Última atualização",
        "inicioINV": "Início do inventário",
        "finalINV": "Término do inventário",
        "duracaoINV": "Duração do inventário",
        "qtyDepositSection": "Seções do depósito",
        "qtySectionSaleFloor": "Seções do piso de venda",
        "qtyProductsCounted": "Produtos contados",
        "qtyItemCounted": "Itens contados",
        "preco_over": "Preço over",
        "productivity": "Produtividade (peças/hora)",
        "percPreparationSaleFloor": "Preparação do piso de venda",
        "percPreparationDeposit": "Preparação do depósito",
        "priceProductsCounted": "Valor total contado",
        "accuracy": "Acuracidade geral",
        "accuracy_dp": "Acuracidade do depósito",
        "accuracy_lj": "Acuracidade da loja",
        "percConclusion": "Progresso geral",
        "percConclusionLoja": "Progresso da loja",
        "percConclusionDeposito": "Progresso do depósito",
        "percConclusion1Contagem": "Conclusão da primeira contagem",
    }

    TABLE_LABELS = {
        "table_secoes": "Progresso das seções da loja",
        "table_secoes2": "Progresso das seções do depósito",
        "table_toppreco": "Itens com maior valor contado",
        "table_topqtd": "Itens com maior quantidade contada",
        "divergencia_table": "Divergências por item",
        "resumo_divergencia_table": "Resumo das divergências",
        "table_conferente": "Conferentes",
    }

    DETAIL_TABLE_GROUPS = {
        "secoes": {"table_secoes", "table_secoes2"},
        "indicadores": {"table_toppreco", "table_topqtd"},
        "divergencias": {"divergencia_table", "resumo_divergencia_table"},
        "conferentes": {"table_conferente"},
    }

    @classmethod
    def respond(cls, user, interpretacao):
        if not settings.INVENTORY_PORTAL_ENABLED:
            return cls._response(
                "A leitura do Portal está desativada neste ambiente. Configure as credenciais da conta técnica e habilite INVENTORY_PORTAL_ENABLED.",
                category="portal_indisponivel",
            )

        start, end = cls._period(interpretacao)
        maximum_days = settings.INVENTORY_PORTAL_MAX_RANGE_DAYS
        if (end - start).days + 1 > maximum_days:
            return cls._response(
                f"Para proteger o Portal, consulte no máximo {maximum_days} dias por vez.",
                category="portal_periodo_invalido",
            )

        try:
            with InventoryPortalClient() as client:
                inventories = client.list_inventories(start=start, end=end)
                inventories = cls._filter_requested(inventories, interpretacao)
                inventories = cls._filter_authorized(user, inventories, interpretacao, start, end)
                if not inventories:
                    return cls._empty_response(interpretacao, start, end)

                if len(inventories) == 1:
                    detail = client.get_inventory_detail(inventories[0])
                    return cls._detail_response(detail, interpretacao)
                if cls._is_detail_query(interpretacao):
                    limit = settings.INVENTORY_PORTAL_MAX_DETAIL_RECORDS
                    details = [
                        client.get_inventory_detail(inventory)
                        for inventory in inventories[:limit]
                    ]
                    return cls._aggregate_detail_response(
                        details,
                        interpretacao,
                        total_inventories=len(inventories),
                    )
                return cls._list_response(inventories, start, end)
        except InventoryPortalConfigurationError:
            return cls._response(
                "As credenciais da conta técnica do Portal ainda não foram configuradas neste ambiente.",
                category="portal_configuracao",
            )
        except InventoryPortalAuthenticationError:
            return cls._response(
                "O Portal recusou a autenticação da conta técnica. A configuração precisa ser revisada.",
                category="portal_autenticacao",
            )
        except InventoryPortalError:
            return cls._response(
                "Não consegui consultar o Portal neste momento. Nenhum dado operacional foi presumido.",
                category="portal_indisponivel",
            )

    @staticmethod
    def _period(interpretacao):
        today = timezone.localdate()
        start = interpretacao.periodo_inicio or interpretacao.data or today
        end = interpretacao.periodo_fim or interpretacao.data or start
        return start, end

    @classmethod
    def _filter_requested(cls, inventories, interpretacao):
        client_code = (
            getattr(interpretacao.cliente, "sigla", "") or
            getattr(interpretacao, "portal_client_code", "")
        ).upper()
        store = cls._normalize_store(interpretacao.loja)
        text = interpretacao.texto
        requested_status = getattr(interpretacao, "portal_status", "any")
        result = []
        for inventory in inventories:
            if client_code and inventory.client_code.upper() != client_code:
                continue
            if store and cls._normalize_store(inventory.store_number) != store:
                continue
            status = cls._normalize(inventory.status)
            current = requested_status == "in_progress" or bool(
                re.search(r"\b(em andamento|agora|neste momento|nesse momento)\b", text)
            )
            if current and "em andamento" not in status:
                continue
            finalized = requested_status == "finalized" or any(
                term in text for term in ("finaliz", "conclu", "encerr")
            )
            if finalized and not (
                "finaliz" in status or "conclu" in status or "encerr" in status
            ):
                continue
            if (requested_status == "scheduled" or "agendad" in text) and "agendad" not in status:
                continue
            if (requested_status == "preparation" or "preparad" in text) and "preparad" not in status:
                continue
            result.append(inventory)
        return result

    @staticmethod
    def _is_detail_query(interpretacao):
        metrics = set(getattr(interpretacao, "portal_metrics", []))
        if metrics - {"summary"}:
            return True
        text = interpretacao.texto
        return bool(re.search(
            r"\b(total de pecas|pecas contadas?|itens? contados?|produtos? contados?|"
            r"produtividade|acuracidade|divergencias?|conferentes?|secoes?|progresso|"
            r"percentual|porcentagem|deposito|piso de venda|informacoes?|detalhes?|"
            r"tudo|todos os dados)\b",
            text,
        ))

    @classmethod
    def _filter_authorized(cls, user, inventories, interpretacao, start, end):
        perfil = getattr(user, "perfil", None)
        if not perfil:
            return []
        if perfil.is_admin and not interpretacao.base:
            return inventories

        queryset = secure_queryset_insumos(
            Inventario.objects.select_related("cliente", "base"),
            user,
            campo_base="base",
        ).filter(data_inicio__range=(start, end))
        if interpretacao.base:
            queryset = queryset.filter(base=interpretacao.base)
        authorized = {
            (
                str(client).upper(),
                cls._normalize_store(store),
                inventory_date,
            )
            for client, store, inventory_date in queryset.values_list(
                "cliente__sigla",
                "loja",
                "data_inicio",
            )
        }
        return [
            inventory
            for inventory in inventories
            if (
                inventory.client_code.upper(),
                cls._normalize_store(inventory.store_number),
                inventory.inventory_date,
            ) in authorized
        ]

    @classmethod
    def _list_response(cls, inventories, start, end):
        lines = [
            f"Encontrei {len(inventories)} inventário(s) no Portal entre {start:%d/%m/%Y} e {end:%d/%m/%Y}.",
            "",
            "STATUS | LOJA | REGIONAL | PREVISÃO | PROGRESSO | CONEXÃO | TIPO",
        ]
        for inventory in inventories[:100]:
            lines.append(
                " | ".join(
                    (
                        inventory.status or "-",
                        inventory.store_display or "-",
                        inventory.regional or "-",
                        inventory.planned_time or "-",
                        inventory.progress or "-",
                        inventory.connection_status or "-",
                        inventory.inventory_type or "-",
                    )
                )
            )
        lines.extend(("", "Fonte: Portal Inventory Brasil — consulta em tempo real."))
        actions = []
        for inventory in inventories[:5]:
            if not inventory.inventory_date:
                continue
            actions.append(
                {
                    "label": inventory.store_display,
                    "pergunta": (
                        f"Detalhe no Portal o inventário {inventory.client_code} "
                        f"loja {inventory.store_number} de {inventory.inventory_date:%d/%m/%Y}"
                    ),
                }
            )
        return cls._response("\n".join(lines), actions=actions)

    @classmethod
    def _detail_response(cls, detail, interpretacao):
        summary = detail.summary
        lines = [
            f"Dados do Portal para {summary.store_display}:",
            "",
            f"- Status: {summary.status or cls._field(detail, 'statusId')}",
            f"- Data: {summary.inventory_date:%d/%m/%Y}" if summary.inventory_date else "- Data: -",
            f"- Regional: {summary.regional or '-'}",
            f"- Líder(es): {summary.leaders or cls._field(detail, 'liderNameBME')}",
            f"- Tipo: {summary.inventory_type or '-'}",
            f"- Previsão de início: {summary.planned_time or '-'}",
            f"- Conexão: {summary.connection_status or '-'}",
            f"- Progresso geral: {detail.progress.get('geral') or summary.progress or '-'}",
            f"- Progresso da loja: {detail.progress.get('loja', '-')}",
            f"- Progresso do depósito: {detail.progress.get('deposito', '-')}",
            f"- Endereço: {cls._address(summary)}",
        ]

        fields = cls._selected_fields(detail, interpretacao)
        if fields:
            lines.extend(("", "INFORMAÇÃO | VALOR"))
            for key, value in fields:
                lines.append(f"{cls.FIELD_LABELS.get(key, key)} | {value}")

        table_ids = cls._selected_tables(detail, interpretacao)
        row_limit = 25 if (
            "all" in getattr(interpretacao, "portal_metrics", []) or
            re.search(r"\b(tudo|todos|todas|completo|completa)\b", interpretacao.texto)
        ) else 10
        for table_id in table_ids:
            rows = list(detail.tables.get(table_id, []))
            if not rows:
                continue
            if table_id == "divergencia_table":
                rows.sort(key=cls._divergence_score, reverse=True)
            headers = list(rows[0].keys())
            lines.extend(("", f"{cls.TABLE_LABELS.get(table_id, table_id)}:", " | ".join(headers)))
            for row in rows[:row_limit]:
                lines.append(" | ".join(str(row.get(header, "")) for header in headers))
            if len(rows) > row_limit:
                lines.append(f"Exibindo {row_limit} de {len(rows)} registros.")

        cls._append_chart_summary(lines, detail)
        consulted_at = detail.fetched_at or timezone.now()
        lines.extend(("", f"Fonte: Portal Inventory Brasil — consultado em {timezone.localtime(consulted_at):%d/%m/%Y às %H:%M}."))
        return cls._response(
            "\n".join(lines),
            actions=[
                {"label": "Ver seções", "pergunta": "Mostre o progresso das seções deste inventário no Portal"},
                {"label": "Ver divergências", "pergunta": "Mostre as divergências deste inventário no Portal"},
                {"label": "Ver conferentes", "pergunta": "Mostre os conferentes deste inventário no Portal"},
                {"label": "Ver produtividade", "pergunta": "Mostre a produtividade deste inventário no Portal"},
            ],
        )

    @classmethod
    def _aggregate_detail_response(cls, details, interpretacao, *, total_inventories):
        item_values = [cls._number(cls._field(detail, "qtyItemCounted")) for detail in details]
        product_values = [cls._number(cls._field(detail, "qtyProductsCounted")) for detail in details]
        productivity_values = [cls._number(cls._field(detail, "productivity")) for detail in details]
        item_values = [value for value in item_values if value is not None]
        product_values = [value for value in product_values if value is not None]
        productivity_values = [value for value in productivity_values if value is not None]

        lines = [
            f"Consolidação em tempo real de {len(details)} inventário(s) consultado(s) no Portal:",
            "",
        ]
        if item_values:
            lines.append(f"- Total de peças/itens contados: {cls._format_number(sum(item_values))}")
        if product_values:
            lines.append(f"- Total de produtos contados: {cls._format_number(sum(product_values))}")
        if productivity_values:
            average = sum(productivity_values) / Decimal(len(productivity_values))
            lines.append(f"- Produtividade média informada: {cls._format_number(average)} peças/hora")

        lines.extend((
            "",
            "LOJA | STATUS | PEÇAS/ITENS CONTADOS | PRODUTOS | PRODUTIVIDADE | PROGRESSO",
        ))
        for detail in details:
            summary = detail.summary
            lines.append(" | ".join((
                summary.store_display or "-",
                summary.status or cls._field(detail, "statusId"),
                cls._field(detail, "qtyItemCounted"),
                cls._field(detail, "qtyProductsCounted"),
                cls._field(detail, "productivity"),
                detail.progress.get("geral") or summary.progress or "-",
            )))

        if (
            "diverg" in interpretacao.texto or
            "divergences" in getattr(interpretacao, "portal_metrics", [])
        ):
            divergence_rows = []
            for detail in details:
                for row in detail.tables.get("divergencia_table", []):
                    divergence_rows.append((detail.summary.store_display, row))
            if divergence_rows:
                divergence_rows.sort(
                    key=lambda item: cls._divergence_score(item[1]),
                    reverse=True,
                )
                headers = list(divergence_rows[0][1].keys())
                lines.extend(("", "ITENS COM DIVERGÊNCIA:", "LOJA | " + " | ".join(headers)))
                for store_display, row in divergence_rows[:25]:
                    lines.append(
                        f"{store_display} | " + " | ".join(str(row.get(header, "")) for header in headers)
                    )

        if total_inventories > len(details):
            lines.extend((
                "",
                f"A consolidação detalhada foi limitada aos primeiros {len(details)} de {total_inventories} inventários para proteger o Portal.",
            ))
        lines.extend(("", "Fonte: Portal Inventory Brasil — consulta em tempo real."))
        return cls._response("\n".join(lines))

    @staticmethod
    def _number(value):
        raw = re.sub(r"[^0-9,.-]", "", str(value or ""))
        if not raw or raw in {"-", ".", ","}:
            return None
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", raw):
            raw = raw.replace(".", "")
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None

    @staticmethod
    def _format_number(value):
        if value == value.to_integral_value():
            return f"{int(value):,}".replace(",", ".")
        return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    @classmethod
    def _divergence_score(cls, row):
        candidates = []
        for key, value in row.items():
            normalized = cls._normalize(key)
            if "diverg" in normalized or "diferenca" in normalized:
                number = cls._number(value)
                if number is not None:
                    candidates.append(abs(number))
        return max(candidates, default=Decimal("-1"))

    @classmethod
    def _selected_fields(cls, detail, interpretacao):
        text = interpretacao.texto
        metrics = set(getattr(interpretacao, "portal_metrics", []))
        all_fields = "all" in metrics or bool(
            re.search(r"\b(tudo|todos|todas|completo|completa|informacoes)\b", text)
        )
        groups = {
            "progresso": {"percConclusion", "percConclusionLoja", "percConclusionDeposito", "percConclusion1Contagem"},
            "produtividade": {"productivity", "qtyPeople", "qtyProductsCounted", "qtyItemCounted", "realtime_alteracao"},
            "acuracidade": {"accuracy", "accuracy_dp", "accuracy_lj"},
            "tempo": {"inicioINV", "finalINV", "duracaoINV", "realtime_alteracao"},
            "preparacao": {"percPreparationSaleFloor", "percPreparationDeposit"},
        }
        wanted = set(cls.FIELD_LABELS) if all_fields else {
            "statusId",
            "qtyPeople",
            "realtime_alteracao",
            "inicioINV",
            "finalINV",
            "duracaoINV",
            "qtyProductsCounted",
            "qtyItemCounted",
            "productivity",
            "accuracy",
        }
        for keyword, keys in groups.items():
            if keyword in text or (keyword == "tempo" and re.search(r"\b(inicio|termino|duracao|horario)\b", text)):
                wanted.update(keys)
        metric_fields = {
            "total_items": {"qtyItemCounted"},
            "total_products": {"qtyProductsCounted"},
            "productivity": groups["produtividade"],
            "accuracy": groups["acuracidade"],
            "progress": groups["progresso"],
            "times": groups["tempo"],
        }
        for metric, keys in metric_fields.items():
            if metric in metrics:
                wanted.update(keys)
        return [
            (key, detail.fields[key])
            for key in cls.FIELD_LABELS
            if key in wanted and detail.fields.get(key) not in (None, "")
        ]

    @classmethod
    def _selected_tables(cls, detail, interpretacao):
        text = interpretacao.texto
        metrics = set(getattr(interpretacao, "portal_metrics", []))
        all_tables = "all" in metrics or bool(
            re.search(r"\b(tudo|todos|todas|completo|completa|informacoes)\b", text)
        )
        if all_tables:
            return [table_id for table_id in cls.TABLE_LABELS if table_id in detail.tables]
        selected = set()
        if re.search(r"\b(secao|secoes|area|areas)\b", text):
            selected.update(cls.DETAIL_TABLE_GROUPS["secoes"])
        if re.search(r"\b(top|item|itens|indicador|indicadores)\b", text):
            selected.update(cls.DETAIL_TABLE_GROUPS["indicadores"])
        if "diverg" in text:
            selected.update(cls.DETAIL_TABLE_GROUPS["divergencias"])
        if re.search(r"\b(conferente|conferentes|equipe)\b", text):
            selected.update(cls.DETAIL_TABLE_GROUPS["conferentes"])
        metric_groups = {
            "sections": "secoes",
            "divergences": "divergencias",
            "conferents": "conferentes",
        }
        for metric, group in metric_groups.items():
            if metric in metrics:
                selected.update(cls.DETAIL_TABLE_GROUPS[group])
        return [table_id for table_id in cls.TABLE_LABELS if table_id in selected]

    @staticmethod
    def _append_chart_summary(lines, detail):
        productivity = detail.charts.get("produtividade", {})
        hours = productivity.get("lst_hour", []) if isinstance(productivity, dict) else []
        values = productivity.get("lst_prod", []) if isinstance(productivity, dict) else []
        if hours and values:
            lines.extend(("", "PRODUTIVIDADE POR PERÍODO | PEÇAS/HORA"))
            for hour, value in list(zip(hours, values))[-10:]:
                lines.append(f"{hour} | {value}")

        advance = detail.charts.get("avanco_geral", {})
        datasets = advance.get("result", {}).get("datasets", []) if isinstance(advance, dict) else []
        if datasets:
            lines.extend(("", "Séries de avanço disponíveis: " + ", ".join(
                str(dataset.get("label", "")).strip()
                for dataset in datasets
                if isinstance(dataset, dict) and dataset.get("label")
            )))

    @classmethod
    def _empty_response(cls, interpretacao, start, end):
        scope = []
        if interpretacao.cliente:
            scope.append(interpretacao.cliente.sigla)
        if interpretacao.loja:
            scope.append(f"loja {interpretacao.loja}")
        requested = " ".join(scope) or "o período solicitado"
        return cls._response(
            f"Não encontrei no Portal inventários autorizados para {requested} entre {start:%d/%m/%Y} e {end:%d/%m/%Y}.",
            category="portal_sem_resultado",
        )

    @staticmethod
    def _field(detail, key):
        return detail.fields.get(key, "-") or "-"

    @staticmethod
    def _address(summary):
        return ", ".join(
            part for part in (summary.address, summary.neighborhood, summary.city) if part
        ) or "-"

    @staticmethod
    def _normalize_store(value):
        value = re.sub(r"\s+", "", str(value or "")).upper()
        return value.lstrip("0") or ("0" if value else "")

    @staticmethod
    def _normalize(value):
        value = unicodedata.normalize("NFKD", str(value or ""))
        return "".join(char for char in value if not unicodedata.combining(char)).lower()

    @staticmethod
    def _response(text, *, category="portal_tempo_real", actions=None):
        return {
            "categoria": category,
            "resposta": text,
            "acoes": actions or [],
        }
