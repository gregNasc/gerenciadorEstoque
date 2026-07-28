from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings

from estoque.models import Base, Empresa, Perfil

from estoque.services.assistente_operacional_service import (
    AssistenteOperacionalService,
    InterpretacaoOperacional,
)
from estoque.services.portal_assistant_service import InventoryPortalAssistantService
from estoque.services.portal_question_interpreter import PortalQuestionPlan
from integracao.clients.inventory_portal import PortalInventoryDetail, PortalInventorySummary
from insumos.models import Cliente, Inventario


def summary(portal_id, store, status="Em andamento"):
    return PortalInventorySummary(
        portal_id=portal_id,
        detail_url=f"https://novoportal.inventorybrasil.com.br/detail/{portal_id}/",
        client_code="OXX",
        store_number=store,
        store_display=f"OXX {store}",
        status=status,
        progress="50%",
        inventory_date=date(2026, 7, 28),
    )


@override_settings(TORY_LLM_ENABLED=False)
class ToryPortalRoutingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("tory_portal_admin")
        self.admin.perfil.role = Perfil.Role.ADMIN
        self.admin.perfil.save()

    def test_routes_now_and_finalized_inventory_questions_to_portal(self):
        now = AssistenteOperacionalService.interpretar(self.admin, "Quais inventários estão rolando agora?")
        finalized = AssistenteOperacionalService.interpretar(self.admin, "Mostre os inventários finalizados hoje")
        concluded = AssistenteOperacionalService.interpretar(self.admin, "Quais inventários foram concluídos hoje?")

        self.assertEqual(now.intencao, "portal_tempo_real")
        self.assertEqual(finalized.intencao, "portal_tempo_real")
        self.assertEqual(concluded.intencao, "portal_tempo_real")

    @override_settings(TORY_LLM_ENABLED=True, OPENAI_API_KEY="test")
    @patch("estoque.services.portal_question_interpreter.PortalQuestionInterpreter.interpret")
    def test_llm_plan_understands_natural_question_without_inventory_word(self, interpret):
        interpret.return_value = PortalQuestionPlan(
            is_portal_query=True,
            status="in_progress",
            store_number="58",
            start_date=date(2026, 7, 28),
            end_date=date(2026, 7, 28),
            metrics=["total_items", "divergences"],
        )

        result = AssistenteOperacionalService.interpretar(
            self.admin,
            "Quanto já contamos na loja 58 e onde erramos mais?",
        )

        self.assertEqual(result.intencao, "portal_tempo_real")
        self.assertEqual(result.loja, "58")
        self.assertEqual(result.portal_status, "in_progress")
        self.assertIn("divergences", result.portal_metrics)


@override_settings(
    INVENTORY_PORTAL_ENABLED=True,
    INVENTORY_PORTAL_MAX_RANGE_DAYS=31,
    INVENTORY_PORTAL_MAX_DETAIL_RECORDS=20,
)
class ToryPortalAnswerTests(SimpleTestCase):
    @patch("estoque.services.portal_assistant_service.timezone.localdate")
    def test_now_queries_today_and_previous_day(self, localdate):
        localdate.return_value = date(2026, 7, 29)
        interpretation = InterpretacaoOperacional(
            pergunta="inventários agora",
            texto="inventarios agora",
            intencao="portal_tempo_real",
            data=date(2026, 7, 29),
            portal_status="in_progress",
        )

        start, end = InventoryPortalAssistantService._period(interpretation)

        self.assertEqual(start, date(2026, 7, 28))
        self.assertEqual(end, date(2026, 7, 29))

    def test_empty_response_distinguishes_portal_filter_and_authorization(self):
        interpretation = InterpretacaoOperacional(
            pergunta="inventários agora",
            texto="inventarios agora",
            intencao="portal_tempo_real",
        )
        row = summary(1, "58", status="Agendado")

        no_portal_rows = InventoryPortalAssistantService._empty_response(
            interpretation,
            date(2026, 7, 28),
            date(2026, 7, 29),
            portal_inventories=[],
            requested_inventories=[],
        )
        no_status_match = InventoryPortalAssistantService._empty_response(
            interpretation,
            date(2026, 7, 28),
            date(2026, 7, 29),
            portal_inventories=[row],
            requested_inventories=[],
        )
        unauthorized = InventoryPortalAssistantService._empty_response(
            interpretation,
            date(2026, 7, 28),
            date(2026, 7, 29),
            portal_inventories=[row],
            requested_inventories=[row],
        )

        self.assertIn("não retornou inventários", no_portal_rows["resposta"])
        self.assertIn("Status disponíveis", no_status_match["resposta"])
        self.assertIn("correspondência autorizada", unauthorized["resposta"])

    @patch("estoque.services.portal_assistant_service.InventoryPortalClient")
    def test_aggregates_items_productivity_and_divergences(self, client_class):
        rows = [summary(1, "58"), summary(2, "59")]
        details = {
            "58": PortalInventoryDetail(
                summary=rows[0],
                fields={"qtyItemCounted": "1.000", "qtyProductsCounted": "100", "productivity": "500"},
                tables={"divergencia_table": [{"Produto": "A", "Divergência": "15"}]},
            ),
            "59": PortalInventoryDetail(
                summary=rows[1],
                fields={"qtyItemCounted": "2.000", "qtyProductsCounted": "200", "productivity": "700"},
                tables={"divergencia_table": [{"Produto": "B", "Divergência": "20"}]},
            ),
        }
        client = client_class.return_value.__enter__.return_value
        client.list_inventories.return_value = rows
        client.get_inventory_detail.side_effect = lambda row: details[row.store_number]
        interpretation = InterpretacaoOperacional(
            pergunta="Total contado agora e maiores divergências",
            texto="total contado agora e maiores divergencias",
            intencao="portal_tempo_real",
            data=date(2026, 7, 28),
            portal_status="in_progress",
            portal_metrics=["total_items", "productivity", "divergences"],
        )
        user = SimpleNamespace(perfil=SimpleNamespace(is_admin=True))

        response = InventoryPortalAssistantService.respond(user, interpretation)

        self.assertIn("3.000", response["resposta"])
        self.assertIn("600", response["resposta"])
        self.assertIn("ITENS COM DIVERGÊNCIA", response["resposta"])
        self.assertLess(response["resposta"].index("OXX 59 | B"), response["resposta"].index("OXX 58 | A"))
        self.assertEqual(client.get_inventory_detail.call_count, 2)


class ToryPortalPermissionTests(TestCase):
    def test_operator_only_sees_portal_inventory_matching_authorized_base(self):
        company = Empresa.objects.create(nome="Empresa Portal")
        allowed_base = Base.objects.create(nome="Base permitida", empresa=company)
        blocked_base = Base.objects.create(nome="Base bloqueada", empresa=company)
        operator = User.objects.create_user("tory_portal_operator")
        operator.perfil.role = Perfil.Role.OPERADOR
        operator.perfil.empresa = company
        operator.perfil.save()
        operator.perfil.regionais.add(allowed_base)
        client = Cliente.objects.create(sigla="OXX", nome="OXXO")
        Inventario.objects.create(
            cliente=client,
            loja="58",
            base=allowed_base,
            data_inicio=date(2026, 7, 28),
            criado_por=operator,
        )
        Inventario.objects.create(
            cliente=client,
            loja="59",
            base=blocked_base,
            data_inicio=date(2026, 7, 28),
            criado_por=operator,
        )
        interpretation = InterpretacaoOperacional(
            pergunta="inventários agora",
            texto="inventarios agora",
            intencao="portal_tempo_real",
        )

        result = InventoryPortalAssistantService._filter_authorized(
            operator,
            [summary(1, "58"), summary(2, "59")],
            interpretation,
            date(2026, 7, 28),
            date(2026, 7, 28),
        )

        self.assertEqual([row.store_number for row in result], ["58"])
