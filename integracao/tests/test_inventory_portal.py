from datetime import date

import httpx
from django.test import SimpleTestCase

from integracao.clients.inventory_portal import (
    InventoryPortalClient,
    PortalInventorySummary,
    parse_inventory_detail,
    parse_inventory_table,
)


LIST_HTML = """
<table><tbody><tr>
  <td><button data-url="/inventory_collect/realtime_view/42/">+</button></td>
  <td>Em andamento</td><td>OXX 0058</td><td>Ana / Bruno</td><td>SP SUL</td>
  <td>22:00</td><td>63%</td><td><div class="bolaVerde"></div></td>
  <td>OFICIAL</td><td>28/07/26</td><td>Rua Um, 10</td><td>Centro</td><td>São Paulo</td>
</tr></tbody></table>
"""

COMPACT_LIST_HTML = """
<table>
  <thead><tr>
    <th></th><th>Status</th><th>Loja</th><th>Previsão</th>
    <th>Progresso</th><th>Conexão</th><th>Endereço</th>
  </tr></thead>
  <tbody><tr>
    <td><button data-url="/inventory_collect/realtime_view/1038/">+</button></td>
    <td>Em Andamento</td><td>MFT 1038</td><td>20:00</td>
    <td><div class="progress-bar" role="progressbar" style="width: 53"></div></td>
    <td><div class="bolaVerde"></div></td>
    <td>AV: VISCONDE DE TAUNAY, 2023</td>
  </tr></tbody>
</table>
"""

DETAIL_HTML = """
<div data-invent-collect="9001"></div>
<input name="qtyPeople" value="12">
<input name="qtyProductsCounted" value="1.234">
<input name="qtyItemCounted" value="25.600">
<input name="productivity" value="530">
<select name="statusId"><option>Agendado</option><option selected>Em andamento</option></select>
<div id="demo-pie-1" data-percent="63%"></div>
<div id="demo-pie-2" data-percent="40%"></div>
<div id="demo-pie-3" data-percent="70%"></div>
<table id="divergencia_table">
  <thead><tr><th>Produto</th><th>Divergência</th></tr></thead>
  <tbody><tr><td>789123</td><td>18</td></tr></tbody>
</table>
"""


class InventoryPortalParserTests(SimpleTestCase):
    def test_parses_inventory_list_and_store_column(self):
        rows = parse_inventory_table(
            LIST_HTML,
            base_url="https://novoportal.inventorybrasil.com.br/",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].portal_id, 42)
        self.assertEqual(rows[0].client_code, "OXX")
        self.assertEqual(rows[0].store_number, "0058")
        self.assertEqual(rows[0].inventory_date, date(2026, 7, 28))
        self.assertIn("Conectado", rows[0].connection_status)

    def test_uses_headers_when_portal_omits_regional_and_type_columns(self):
        rows = parse_inventory_table(
            COMPACT_LIST_HTML,
            base_url="https://novoportal.inventorybrasil.com.br/",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].store_display, "MFT 1038")
        self.assertEqual(rows[0].regional, "")
        self.assertEqual(rows[0].planned_time, "20:00")
        self.assertEqual(rows[0].progress, "53%")
        self.assertEqual(rows[0].inventory_type, "")
        self.assertEqual(rows[0].address, "AV: VISCONDE DE TAUNAY, 2023")

    def test_parses_modal_fields_progress_and_tables(self):
        summary = PortalInventorySummary(
            portal_id=42,
            detail_url="https://novoportal.inventorybrasil.com.br/inventory_collect/realtime_view/42/",
            client_code="OXX",
            store_number="0058",
            store_display="OXX 0058",
        )

        detail = parse_inventory_detail(DETAIL_HTML, summary=summary)

        self.assertEqual(detail.collect_id, "9001")
        self.assertEqual(detail.fields["qtyItemCounted"], "25.600")
        self.assertEqual(detail.fields["statusId"], "Em andamento")
        self.assertEqual(detail.progress["geral"], "63%")
        self.assertEqual(
            detail.tables["divergencia_table"][0],
            {"Produto": "789123", "Divergência": "18"},
        )


class InventoryPortalClientTests(SimpleTestCase):
    def test_authenticates_and_reads_list_without_write_requests(self):
        requests = []

        def handler(request):
            requests.append(request)
            if request.method == "GET" and request.url.path == "/":
                return httpx.Response(
                    200,
                    text='<input name="csrfmiddlewaretoken" value="csrf-test">',
                )
            if request.method == "POST" and request.url.path == "/":
                return httpx.Response(200, text="Dashboard")
            if "inventariodata_list" in request.url.path:
                return httpx.Response(200, json={"html_form": LIST_HTML})
            return httpx.Response(404)

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http_client.close)
        client = InventoryPortalClient(
            base_url="https://novoportal.inventorybrasil.com.br/",
            username="conta-tecnica",
            password="segredo",
            http_client=http_client,
        )

        rows = client.list_inventories(start=date(2026, 7, 28), end=date(2026, 7, 28))

        self.assertEqual(len(rows), 1)
        self.assertEqual([request.method for request in requests], ["GET", "POST", "GET"])
        self.assertIn("28-07-2026/28-07-2026", requests[-1].url.path)
