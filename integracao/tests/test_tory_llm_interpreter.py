import json

import httpx
from django.test import SimpleTestCase, override_settings

from estoque.services.portal_question_interpreter import PortalQuestionInterpreter


@override_settings(
    TORY_LLM_ENABLED=True,
    OPENAI_API_KEY="test-key",
    TORY_LLM_MODEL="gpt-5.6-sol",
    TORY_LLM_TIMEOUT=5,
)
class PortalQuestionInterpreterTests(SimpleTestCase):
    def test_returns_validated_structured_plan(self):
        captured = {}

        def handler(request):
            captured.update(json.loads(request.content))
            result = {
                "intent": "portal_tempo_real",
                "confidence": 0.96,
                "is_follow_up": False,
                "is_portal_query": True,
                "status": "in_progress",
                "client_code": "OXX",
                "store_number": "58",
                "start_date": "2026-07-28",
                "end_date": "2026-07-28",
                "metrics": ["total_items", "productivity", "divergences"],
            }
            return httpx.Response(
                200,
                json={
                    "output": [{
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(result)}],
                    }]
                },
            )

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http_client.close)

        plan = PortalQuestionInterpreter.interpret(
            "Quanto já contamos na OXXO 58 agora e quais as piores diferenças?",
            http_client=http_client,
        )

        self.assertTrue(plan.is_portal_query)
        self.assertEqual(plan.intent, "portal_tempo_real")
        self.assertGreater(plan.confidence, 0.9)
        self.assertEqual(plan.status, "in_progress")
        self.assertEqual(plan.store_number, "58")
        self.assertIn("divergences", plan.metrics)
        self.assertFalse(captured["store"])
        self.assertEqual(captured["text"]["format"]["type"], "json_schema")
        self.assertTrue(captured["text"]["format"]["strict"])
        self.assertIn("intent", captured["text"]["format"]["schema"]["required"])

    def test_validates_general_intent_and_confidence(self):
        payload = {
            "intent": "equipamentos",
            "confidence": 2,
            "is_follow_up": True,
            "is_portal_query": False,
            "status": "invalid",
            "client_code": "",
            "store_number": "",
            "start_date": None,
            "end_date": None,
            "metrics": ["invalid"],
        }

        plan = PortalQuestionInterpreter._validate(payload)

        self.assertEqual(plan.intent, "equipamentos")
        self.assertEqual(plan.confidence, 1)
        self.assertTrue(plan.is_follow_up)
        self.assertFalse(plan.is_portal_query)
        self.assertEqual(plan.status, "any")

    def test_failure_falls_back_without_exposing_exception(self):
        def handler(request):
            return httpx.Response(503, text="temporary")

        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http_client.close)

        with self.assertLogs("integracao.tory_llm", level="ERROR"):
            plan = PortalQuestionInterpreter.interpret(
                "Como estão as lojas agora?",
                http_client=http_client,
            )

        self.assertIsNone(plan)
