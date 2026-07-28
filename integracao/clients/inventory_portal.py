import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from django.conf import settings
from django.utils import timezone

from integracao.exceptions import (
    InventoryPortalAuthenticationError,
    InventoryPortalConfigurationError,
    InventoryPortalError,
    InventoryPortalResponseError,
    InventoryPortalTransportError,
)


logger = logging.getLogger("integracao.inventory_portal")


def _clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _classes(attrs):
    return set(dict(attrs).get("class", "").split())


def _parse_portal_date(value):
    value = _clean_text(value)
    for pattern in (r"^(\d{2})/(\d{2})/(\d{2})$", r"^(\d{2})/(\d{2})/(\d{4})$"):
        match = re.match(pattern, value)
        if not match:
            continue
        day, month, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _split_store(value):
    match = re.match(r"^(\S+)\s+(.+)$", _clean_text(value))
    if not match:
        return "", _clean_text(value)
    return match.group(1).upper(), match.group(2).strip()


def _normalize_column_name(value):
    normalized = unicodedata.normalize("NFKD", _clean_text(value))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()


_INVENTORY_COLUMN_ALIASES = {
    "status": {"status", "estado", "situacao"},
    "store": {"loja", "tienda", "local"},
    "leaders": {"lider", "lideres", "lider es", "leader", "leaders"},
    "regional": {"regional", "regiao", "region"},
    "planned_time": {
        "previsao",
        "previsao de inicio",
        "hora",
        "hora prevista",
        "inicio previsto",
    },
    "progress": {"progresso", "progreso", "avance", "percentual"},
    "connection": {"conexao", "conexion", "conectividade"},
    "inventory_type": {"tipo", "tipo de inventario"},
    "inventory_date": {"data", "fecha", "data do inventario"},
    "address": {"endereco", "direccion", "morada"},
    "neighborhood": {"bairro", "comuna", "distrito"},
    "city": {"cidade", "ciudad", "municipio"},
}


def _inventory_column_key(value):
    normalized = _normalize_column_name(value)
    if not normalized:
        return ""
    for key, aliases in _INVENTORY_COLUMN_ALIASES.items():
        if normalized in aliases:
            return key
    return ""


def _map_inventory_row(row):
    cells = row["cells"]
    candidates = (row.get("cell_labels", []), row.get("headers", []))
    for labels in candidates:
        if len(labels) != len(cells):
            continue
        mapped = {}
        for label, value in zip(labels, cells):
            key = _inventory_column_key(label)
            if key and key not in mapped:
                mapped[key] = value
        if "store" in mapped:
            if not mapped.get("progress"):
                mapped["progress"] = next(
                    (
                        value
                        for value in cells
                        if re.fullmatch(r"\s*[0-9]+(?:[.,][0-9]+)?\s*%\s*", value)
                    ),
                    "",
                )
            return mapped
    return {}


@dataclass(frozen=True)
class PortalInventorySummary:
    portal_id: int | None
    detail_url: str
    client_code: str
    store_number: str
    store_display: str
    status: str = ""
    leaders: str = ""
    regional: str = ""
    planned_time: str = ""
    progress: str = ""
    connection_status: str = ""
    inventory_type: str = ""
    inventory_date: date | None = None
    address: str = ""
    neighborhood: str = ""
    city: str = ""


@dataclass(frozen=True)
class PortalInventoryDetail:
    summary: PortalInventorySummary
    fields: dict[str, str] = field(default_factory=dict)
    progress: dict[str, str] = field(default_factory=dict)
    tables: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    charts: dict[str, object] = field(default_factory=dict)
    collect_id: str = ""
    fetched_at: object | None = None


class _InventoryTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._row = None
        self._cell = None
        self._cell_label = ""
        self._cell_progress = ""
        self._header_cell = None
        self._table_headers = []
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in {"script", "style"}:
            self._ignored += 1
            return
        if self._ignored:
            return
        if tag == "table":
            self._table_headers = []
        elif tag == "tr":
            self._row = {
                "cells": [],
                "cell_labels": [],
                "detail_url": "",
                "connection": "",
            }
        elif tag == "th":
            self._header_cell = []
        elif tag == "td" and self._row is not None:
            self._cell = []
            self._cell_progress = ""
            self._cell_label = _clean_text(
                attrs_dict.get("data-label")
                or attrs_dict.get("data-title")
                or attrs_dict.get("aria-label")
                or ""
            )
        elif tag == "button" and self._row is not None and attrs_dict.get("data-url"):
            self._row["detail_url"] = attrs_dict["data-url"]
        elif tag == "div" and self._row is not None:
            classes = _classes(attrs)
            if self._cell is not None and (
                "progress-bar" in classes or attrs_dict.get("role") == "progressbar"
            ):
                progress = _clean_text(
                    attrs_dict.get("aria-valuenow") or attrs_dict.get("data-percent") or ""
                )
                if progress and not progress.endswith("%"):
                    progress += "%"
                if not progress:
                    style_match = re.search(
                        r"(?:^|;)\s*width\s*:\s*([0-9]+(?:[.,][0-9]+)?)\s*%?",
                        attrs_dict.get("style", ""),
                        re.IGNORECASE,
                    )
                    if style_match:
                        progress = f"{style_match.group(1)}%"
                self._cell_progress = progress
            if "bolaVerde" in classes:
                self._row["connection"] = "Conectado nos últimos 15 minutos"
            elif "bolaVermelha" in classes:
                self._row["connection"] = "Sem conexão nos últimos 15 minutos"
            elif "bolaAzul" in classes:
                self._row["connection"] = "Nenhuma conexão registrada"

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._ignored:
            self._ignored -= 1
            return
        if self._ignored:
            return
        if tag == "th" and self._header_cell is not None:
            self._table_headers.append(_clean_text(" ".join(self._header_cell)))
            self._header_cell = None
        elif tag == "td" and self._row is not None and self._cell is not None:
            cell_text = _clean_text(" ".join(self._cell))
            self._row["cells"].append(self._cell_progress or cell_text)
            self._row["cell_labels"].append(self._cell_label)
            self._cell = None
            self._cell_label = ""
            self._cell_progress = ""
        elif tag == "tr" and self._row is not None:
            if self._row["cells"] and self._row["detail_url"]:
                self._row["headers"] = list(self._table_headers)
                self.rows.append(self._row)
            self._row = None
            self._cell = None

    def handle_data(self, data):
        if self._ignored:
            return
        if self._cell is not None:
            self._cell.append(data)
        if self._header_cell is not None:
            self._header_cell.append(data)


class _CsrfParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.token = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "input" and attrs_dict.get("name") == "csrfmiddlewaretoken":
            self.token = attrs_dict.get("value", "")


class _InventoryDetailParser(HTMLParser):
    PROGRESS_IDS = {
        "demo-pie-1": "geral",
        "demo-pie-2": "deposito",
        "demo-pie-3": "loja",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.labels = {}
        self.controls = {}
        self.progress = {}
        self.tables = {}
        self.collect_id = ""
        self._ignored = 0
        self._label_for = ""
        self._label_text = []
        self._textarea = ""
        self._textarea_text = []
        self._select = ""
        self._selected_option = False
        self._option_text = []
        self._table_id = ""
        self._table_headers = []
        self._table_rows = []
        self._table_row = None
        self._table_cell = None
        self._in_thead = False
        self._in_tbody = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in {"script", "style"}:
            self._ignored += 1
            return
        if self._ignored:
            return

        element_id = attrs_dict.get("id", "")
        if element_id in self.PROGRESS_IDS:
            self.progress[self.PROGRESS_IDS[element_id]] = _clean_text(
                attrs_dict.get("data-percent", "")
            )
        if attrs_dict.get("data-invent-collect"):
            self.collect_id = _clean_text(attrs_dict["data-invent-collect"])

        if tag == "label" and attrs_dict.get("for"):
            self._label_for = attrs_dict["for"]
            self._label_text = []
        elif tag == "input":
            key = attrs_dict.get("name") or element_id.removeprefix("id_")
            input_type = str(attrs_dict.get("type") or "text").lower()
            if key and input_type not in {"hidden", "submit", "button", "file"}:
                self.controls[key] = _clean_text(attrs_dict.get("value", ""))
        elif tag == "textarea":
            self._textarea = attrs_dict.get("name") or element_id.removeprefix("id_")
            self._textarea_text = []
        elif tag == "select":
            self._select = attrs_dict.get("name") or element_id.removeprefix("id_")
        elif tag == "option" and self._select:
            self._selected_option = "selected" in attrs_dict
            self._option_text = []
        elif tag == "table":
            self._table_id = element_id or f"table_{len(self.tables) + 1}"
            self._table_headers = []
            self._table_rows = []
        elif tag == "thead" and self._table_id:
            self._in_thead = True
        elif tag == "tbody" and self._table_id:
            self._in_tbody = True
        elif tag == "tr" and self._table_id and (self._in_thead or self._in_tbody):
            self._table_row = []
        elif tag in {"th", "td"} and self._table_row is not None:
            self._table_cell = []

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._ignored:
            self._ignored -= 1
            return
        if self._ignored:
            return
        if tag == "label" and self._label_for:
            self.labels[self._label_for.removeprefix("id_")] = _clean_text(
                " ".join(self._label_text)
            ).rstrip(":")
            self._label_for = ""
            self._label_text = []
        elif tag == "textarea" and self._textarea:
            self.controls[self._textarea] = _clean_text(" ".join(self._textarea_text))
            self._textarea = ""
            self._textarea_text = []
        elif tag == "option" and self._select:
            if self._selected_option:
                self.controls[self._select] = _clean_text(" ".join(self._option_text))
            self._selected_option = False
            self._option_text = []
        elif tag == "select":
            self._select = ""
        elif tag in {"th", "td"} and self._table_cell is not None:
            self._table_row.append(_clean_text(" ".join(self._table_cell)))
            self._table_cell = None
        elif tag == "tr" and self._table_row is not None:
            if self._in_thead and not self._table_headers:
                self._table_headers = self._deduplicate_headers(self._table_row)
            elif self._in_tbody and any(self._table_row):
                self._table_rows.append(self._table_row)
            self._table_row = None
        elif tag == "thead":
            self._in_thead = False
        elif tag == "tbody":
            self._in_tbody = False
        elif tag == "table" and self._table_id:
            headers = self._table_headers
            rows = []
            for values in self._table_rows:
                if not headers:
                    headers = [f"coluna_{index + 1}" for index in range(len(values))]
                if len(values) < len(headers):
                    values = values + [""] * (len(headers) - len(values))
                rows.append(dict(zip(headers, values[: len(headers)])))
            self.tables[self._table_id] = rows
            self._table_id = ""
            self._table_headers = []
            self._table_rows = []

    def handle_data(self, data):
        if self._ignored:
            return
        if self._label_for:
            self._label_text.append(data)
        if self._textarea:
            self._textarea_text.append(data)
        if self._select and self._option_text is not None:
            self._option_text.append(data)
        if self._table_cell is not None:
            self._table_cell.append(data)

    @staticmethod
    def _deduplicate_headers(headers):
        result = []
        counts = {}
        for index, header in enumerate(headers):
            header = header or f"coluna_{index + 1}"
            counts[header] = counts.get(header, 0) + 1
            suffix = f"_{counts[header]}" if counts[header] > 1 else ""
            result.append(f"{header}{suffix}")
        return result


def parse_inventory_table(html, *, base_url):
    parser = _InventoryTableParser()
    parser.feed(str(html or ""))
    inventories = []
    for row in parser.rows:
        cells = row["cells"]
        mapped = _map_inventory_row(row)
        if mapped:
            values = mapped
        elif len(cells) >= 10:
            # Compatibilidade com a versão antiga do Portal, cujo fragmento AJAX
            # não incluía cabeçalhos e tinha uma ordem fixa de 13 colunas.
            values = {
                "status": cells[1],
                "store": cells[2],
                "leaders": cells[3],
                "regional": cells[4],
                "planned_time": cells[5],
                "progress": cells[6],
                "inventory_type": cells[8],
                "inventory_date": cells[9],
                "address": cells[10] if len(cells) > 10 else "",
                "neighborhood": cells[11] if len(cells) > 11 else "",
                "city": cells[12] if len(cells) > 12 else "",
            }
        else:
            continue

        store_display = values.get("store", "")
        if not store_display:
            continue
        client_code, store_number = _split_store(store_display)
        detail_url = urljoin(base_url.rstrip("/") + "/", row["detail_url"])
        id_match = re.search(r"/(\d+)/?$", urlparse(detail_url).path)
        inventories.append(
            PortalInventorySummary(
                portal_id=int(id_match.group(1)) if id_match else None,
                detail_url=detail_url,
                client_code=client_code,
                store_number=store_number,
                store_display=store_display,
                status=values.get("status", ""),
                leaders=values.get("leaders", ""),
                regional=values.get("regional", ""),
                planned_time=values.get("planned_time", ""),
                progress=values.get("progress", ""),
                connection_status=row["connection"] or values.get("connection", ""),
                inventory_type=values.get("inventory_type", ""),
                inventory_date=_parse_portal_date(values.get("inventory_date", "")),
                address=values.get("address", ""),
                neighborhood=values.get("neighborhood", ""),
                city=values.get("city", ""),
            )
        )
    return inventories


def parse_inventory_detail(html, *, summary):
    parser = _InventoryDetailParser()
    parser.feed(str(html or ""))
    fields = {}
    for key, value in parser.controls.items():
        if value not in (None, ""):
            fields[key] = value
    return PortalInventoryDetail(
        summary=summary,
        fields=fields,
        progress={key: value for key, value in parser.progress.items() if value},
        tables={key: value for key, value in parser.tables.items() if value},
        collect_id=parser.collect_id,
        fetched_at=timezone.now(),
    )


class InventoryPortalClient:
    """Lê a interface autenticada do Portal sem executar alterações operacionais."""

    LOGIN_MARKERS = ('name="username"', "Inventory Brasil - Login")

    def __init__(
        self,
        *,
        base_url=None,
        username=None,
        password=None,
        timeout=None,
        http_client=None,
    ):
        self.base_url = (base_url or settings.INVENTORY_PORTAL_URL).rstrip("/") + "/"
        self.username = username or settings.INVENTORY_PORTAL_USERNAME
        self.password = password or settings.INVENTORY_PORTAL_PASSWORD
        self.timeout = timeout if timeout is not None else settings.INVENTORY_PORTAL_TIMEOUT
        self._validate_configuration()
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            verify=True,
            headers={"User-Agent": "gerenciadorEstoque-Tory/1.0"},
        )
        self._owns_client = http_client is None
        self._authenticated = False

    def _validate_configuration(self):
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise InventoryPortalConfigurationError(
                "INVENTORY_PORTAL_URL deve ser uma URL HTTPS válida."
            )
        if not self.username or not self.password:
            raise InventoryPortalConfigurationError(
                "As credenciais do Portal não foram configuradas."
            )
        if self.timeout <= 0:
            raise InventoryPortalConfigurationError(
                "INVENTORY_PORTAL_TIMEOUT deve ser maior que zero."
            )

    def close(self):
        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _url(self, endpoint):
        url = urljoin(self.base_url, str(endpoint or "").lstrip("/"))
        parsed = urlparse(url)
        expected = urlparse(self.base_url)
        if (parsed.scheme, parsed.netloc) != (expected.scheme, expected.netloc):
            raise InventoryPortalConfigurationError("Endpoint externo inválido.")
        return url

    def _ensure_same_origin(self, response):
        parsed = urlparse(str(response.url))
        expected = urlparse(self.base_url)
        if (parsed.scheme, parsed.netloc) != (expected.scheme, expected.netloc):
            raise InventoryPortalResponseError("O Portal redirecionou para um domínio inesperado.")

    def _send(self, method, url, **kwargs):
        try:
            response = self._client.request(method, url, timeout=self.timeout, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise InventoryPortalTransportError(
                "Falha de transporte ao acessar o Portal Inventory Brasil."
            ) from exc
        self._ensure_same_origin(response)
        if response.status_code >= 500:
            raise InventoryPortalResponseError("O Portal Inventory Brasil está indisponível.")
        if response.status_code >= 400:
            raise InventoryPortalResponseError(
                f"O Portal recusou a consulta ({response.status_code})."
            )
        return response

    @classmethod
    def _is_login_page(cls, response):
        text = response.text or ""
        return any(marker in text for marker in cls.LOGIN_MARKERS)

    def authenticate(self):
        if self._authenticated:
            return
        login_url = self._url("")
        response = self._send("GET", login_url, headers={"Accept": "text/html"})
        parser = _CsrfParser()
        parser.feed(response.text)
        csrf_token = parser.token or self._client.cookies.get("csrftoken", "")
        if not csrf_token:
            raise InventoryPortalAuthenticationError(
                "O Portal não forneceu o token de autenticação esperado."
            )
        response = self._send(
            "POST",
            login_url,
            data={
                "username": self.username,
                "password": self.password,
                "csrfmiddlewaretoken": csrf_token,
                "next": "/realtime/inventario_data/",
            },
            headers={"Referer": login_url, "Accept": "text/html"},
        )
        if self._is_login_page(response):
            logger.warning("inventory_portal_auth_failed")
            raise InventoryPortalAuthenticationError(
                "O Portal recusou a conta técnica configurada."
            )
        self._authenticated = True
        logger.info("inventory_portal_auth_success")

    def _get_html_envelope(self, endpoint):
        self.authenticate()
        response = self._send(
            "GET",
            self._url(endpoint),
            headers={"Accept": "application/json"},
        )
        if self._is_login_page(response):
            self._authenticated = False
            raise InventoryPortalAuthenticationError("A sessão do Portal expirou.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise InventoryPortalResponseError("O Portal retornou JSON inválido.") from exc
        html = payload.get("html_form") if isinstance(payload, dict) else None
        if not isinstance(html, str):
            raise InventoryPortalResponseError("O Portal retornou um envelope inesperado.")
        return html

    def _get_optional_json(self, endpoint):
        try:
            response = self._send(
                "GET",
                self._url(endpoint),
                headers={"Accept": "application/json"},
            )
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except (InventoryPortalError, ValueError):
            logger.warning("inventory_portal_optional_data_failed endpoint=%s", endpoint)
            return {}

    def list_inventories(self, *, start, end):
        if not isinstance(start, date) or not isinstance(end, date) or end < start:
            raise InventoryPortalConfigurationError("Período de consulta do Portal inválido.")
        endpoint = (
            "inventory_collect/inventariodata_list/"
            f"{start:%d-%m-%Y}/{end:%d-%m-%Y}/"
        )
        html = self._get_html_envelope(endpoint)
        inventories = parse_inventory_table(html, base_url=self.base_url)
        logger.info(
            "inventory_portal_list start=%s end=%s records=%s",
            start,
            end,
            len(inventories),
        )
        return inventories

    def get_inventory_detail(self, summary):
        detail_url = self._url(summary.detail_url)
        html = self._get_html_envelope(detail_url)
        detail = parse_inventory_detail(html, summary=summary)
        charts = {}
        if summary.portal_id:
            charts["produtividade"] = self._get_optional_json(
                f"realtime/dashbord_realtime/{summary.portal_id}/60/"
            )
        if detail.collect_id:
            charts["avanco_geral"] = self._get_optional_json(
                f"realtime/grafico_avanco_geral/{detail.collect_id}/60/"
            )
        return PortalInventoryDetail(
            summary=detail.summary,
            fields=detail.fields,
            progress=detail.progress,
            tables=detail.tables,
            charts={key: value for key, value in charts.items() if value},
            collect_id=detail.collect_id,
            fetched_at=detail.fetched_at,
        )
