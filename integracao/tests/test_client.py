import httpx
from django.test import SimpleTestCase

from integracao.clients.inventory_planning import InventoryPlanningClient
from integracao.exceptions import (
    InventoryPlanningAuthenticationError,
    InventoryPlanningConfigurationError,
    InventoryPlanningTransportError,
)


class InventoryPlanningClientTests(SimpleTestCase):
    base_url = "https://planning.example.test/api/integration/v1"
    api_key = "ipk_super_secreta"

    def _client(self, handler, **kwargs):
        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http_client.close)
        return InventoryPlanningClient(
            base_url=self.base_url,
            api_key=self.api_key,
            http_client=http_client,
            backoff_base=0,
            random_uniform=lambda _start, _end: 0,
            **kwargs,
        )

    def test_authentication_and_pagination_use_per_page_100(self):
        requests = []

        def handler(request):
            requests.append(request)
            page = int(request.url.params["page"])
            return httpx.Response(
                200,
                json={
                    "data": {
                        "items": [{"id": f"event-{page}"}],
                        "meta": {"page": page, "perPage": 100, "total": 2, "pageCount": 2},
                    }
                },
            )

        pages = list(self._client(handler).iter_pages("/events"))

        self.assertEqual(len(pages), 2)
        self.assertEqual([page[0][0]["id"] for page in pages], ["event-1", "event-2"])
        self.assertTrue(all(request.headers["X-API-Key"] == self.api_key for request in requests))
        self.assertTrue(all(request.url.params["perPage"] == "100" for request in requests))

    def test_timeout_is_retried_and_raises_safe_error(self):
        sleeps = []

        def handler(request):
            raise httpx.ReadTimeout("timeout com cpf 12345678901", request=request)

        client = self._client(handler, max_retries=1, sleep=sleeps.append)
        with self.assertRaises(InventoryPlanningTransportError) as captured:
            list(client.iter_pages("/events"))
        self.assertEqual(len(sleeps), 1)
        self.assertNotIn("12345678901", str(captured.exception))

    def test_retry_after_is_respected_after_429(self):
        sleeps = []
        attempts = 0

        def handler(request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": {"message": "wait"}})
            return httpx.Response(200, json={"data": []})

        pages = list(self._client(handler, max_retries=1, sleep=sleeps.append).iter_pages("/regions"))
        self.assertEqual(len(pages), 1)
        self.assertEqual(sleeps, [2.0])

    def test_500_is_retried(self):
        attempts = 0

        def handler(request):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(503, json={"error": {"message": "temporary"}})
            return httpx.Response(200, json={"data": []})

        list(self._client(handler, max_retries=1, sleep=lambda _delay: None).iter_pages("/clients"))
        self.assertEqual(attempts, 2)

    def test_401_and_403_are_not_retried(self):
        for status in (401, 403):
            with self.subTest(status=status):
                attempts = 0

                def handler(request):
                    nonlocal attempts
                    attempts += 1
                    return httpx.Response(status, json={"error": {"message": "denied"}})

                with self.assertRaises(InventoryPlanningAuthenticationError):
                    list(self._client(handler, max_retries=3).iter_pages("/events"))
                self.assertEqual(attempts, 1)

    def test_logs_do_not_expose_key_or_sensitive_response(self):
        def handler(request):
            return httpx.Response(
                401,
                json={"error": {"message": f"{self.api_key} CPF 12345678901"}},
            )

        with self.assertLogs("integracao.inventory_planning", level="ERROR") as logs:
            with self.assertRaises(InventoryPlanningAuthenticationError):
                list(self._client(handler).iter_pages("/events"))
        output = " ".join(logs.output)
        self.assertNotIn(self.api_key, output)
        self.assertNotIn("12345678901", output)

    def test_http_url_is_rejected_before_request(self):
        with self.assertRaises(InventoryPlanningConfigurationError):
            InventoryPlanningClient(
                base_url="http://planning.example.test/api",
                api_key=self.api_key,
            )

