import logging
import random
import time
from datetime import datetime, timezone as dt_timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import httpx
from django.conf import settings

from integracao.exceptions import (
    InventoryPlanningAuthenticationError,
    InventoryPlanningConfigurationError,
    InventoryPlanningRateLimitError,
    InventoryPlanningResponseError,
    InventoryPlanningTransportError,
)


logger = logging.getLogger("integracao.inventory_planning")


class InventoryPlanningClient:
    RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        base_url=None,
        api_key=None,
        timeout=None,
        max_retries=None,
        backoff_base=None,
        http_client=None,
        sleep=None,
        random_uniform=None,
    ):
        self.base_url = (base_url or settings.INVENTORY_PLANNING_API_URL).rstrip("/") + "/"
        self.api_key = api_key or settings.INVENTORY_PLANNING_API_KEY
        self.timeout = timeout if timeout is not None else settings.INVENTORY_PLANNING_TIMEOUT
        self.max_retries = (
            max_retries
            if max_retries is not None
            else settings.INVENTORY_PLANNING_MAX_RETRIES
        )
        self.backoff_base = (
            backoff_base
            if backoff_base is not None
            else settings.INVENTORY_PLANNING_BACKOFF_BASE
        )
        self._sleep = sleep or time.sleep
        self._random_uniform = random_uniform or random.uniform
        self._validate_configuration()
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=False,
            verify=True,
        )
        self._owns_client = http_client is None

    def _validate_configuration(self):
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise InventoryPlanningConfigurationError(
                "INVENTORY_PLANNING_API_URL deve ser uma URL HTTPS válida."
            )
        if not self.api_key:
            raise InventoryPlanningConfigurationError(
                "INVENTORY_PLANNING_API_KEY não foi configurada."
            )
        if self.timeout <= 0:
            raise InventoryPlanningConfigurationError(
                "INVENTORY_PLANNING_TIMEOUT deve ser maior que zero."
            )
        if self.max_retries < 0:
            raise InventoryPlanningConfigurationError(
                "INVENTORY_PLANNING_MAX_RETRIES não pode ser negativo."
            )

    def close(self):
        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _url(self, endpoint):
        endpoint = endpoint.lstrip("/")
        url = urljoin(self.base_url, endpoint)
        if urlparse(url).netloc != urlparse(self.base_url).netloc:
            raise InventoryPlanningConfigurationError("Endpoint externo inválido.")
        return url

    def _retry_delay(self, response, attempt):
        retry_after = response.headers.get("Retry-After") if response is not None else None
        if retry_after:
            try:
                return max(float(retry_after), 0)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=dt_timezone.utc)
                    now = datetime.now(dt_timezone.utc)
                    return max((retry_at - now).total_seconds(), 0)
                except (TypeError, ValueError, OverflowError):
                    pass
        base = self.backoff_base * (2 ** attempt)
        return base + self._random_uniform(0, max(base / 4, 0))

    def _request(self, endpoint, *, params=None):
        url = self._url(endpoint)
        headers = {
            "Accept": "application/json",
            "X-API-Key": self.api_key,
        }
        last_transport_error = None

        for attempt in range(self.max_retries + 1):
            response = None
            try:
                response = self._client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_transport_error = exc
                if attempt >= self.max_retries:
                    break
                delay = self._retry_delay(None, attempt)
                logger.warning(
                    "inventory_planning_retry endpoint=%s reason=transport attempt=%s delay=%.3f",
                    endpoint,
                    attempt + 1,
                    delay,
                )
                self._sleep(delay)
                continue

            if response.status_code in (401, 403):
                logger.error(
                    "inventory_planning_auth_failed endpoint=%s status=%s",
                    endpoint,
                    response.status_code,
                )
                raise InventoryPlanningAuthenticationError(
                    f"Autenticação da Inventory Planning API recusada ({response.status_code})."
                )

            if response.status_code in self.RETRYABLE_STATUS or response.status_code >= 500:
                if attempt >= self.max_retries:
                    if response.status_code == 429:
                        raise InventoryPlanningRateLimitError(
                            "Limite da Inventory Planning API excedido após as tentativas configuradas."
                        )
                    raise InventoryPlanningResponseError(
                        f"Inventory Planning API indisponível ({response.status_code})."
                    )
                delay = self._retry_delay(response, attempt)
                logger.warning(
                    "inventory_planning_retry endpoint=%s status=%s attempt=%s delay=%.3f",
                    endpoint,
                    response.status_code,
                    attempt + 1,
                    delay,
                )
                self._sleep(delay)
                continue

            if response.is_redirect:
                raise InventoryPlanningResponseError(
                    "A Inventory Planning API respondeu com redirecionamento não permitido."
                )
            if response.status_code >= 400:
                raise InventoryPlanningResponseError(
                    f"Inventory Planning API recusou a requisição ({response.status_code})."
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise InventoryPlanningResponseError(
                    "Inventory Planning API retornou JSON inválido."
                ) from exc
            if not isinstance(payload, dict) or "data" not in payload:
                raise InventoryPlanningResponseError(
                    "Inventory Planning API retornou um envelope inválido."
                )
            logger.info(
                "inventory_planning_request endpoint=%s status=%s",
                endpoint,
                response.status_code,
            )
            return payload["data"], response.headers

        raise InventoryPlanningTransportError(
            "Falha de transporte ao acessar a Inventory Planning API."
        ) from last_transport_error

    def iter_pages(self, endpoint, *, params=None):
        page = 1
        page_count = None
        base_params = dict(params or {})
        base_params["perPage"] = 100

        while page_count is None or page <= page_count:
            request_params = {**base_params, "page": page}
            data, headers = self._request(endpoint, params=request_params)
            if isinstance(data, list):
                yield data, {"page": 1, "pageCount": 1, "perPage": len(data)}, headers
                return
            if not isinstance(data, dict):
                raise InventoryPlanningResponseError(
                    "Lista paginada da Inventory Planning API possui formato inválido."
                )
            items = data.get("items")
            meta = data.get("meta")
            if not isinstance(items, list) or not isinstance(meta, dict):
                raise InventoryPlanningResponseError(
                    "Paginação da Inventory Planning API possui formato inválido."
                )
            current_page = int(meta.get("page", page))
            page_count = int(meta.get("pageCount", current_page))
            if current_page != page or page_count < current_page:
                raise InventoryPlanningResponseError(
                    "Metadados de paginação da Inventory Planning API são inconsistentes."
                )
            yield items, meta, headers
            page += 1

    def get_item(self, endpoint):
        data, _headers = self._request(endpoint)
        if not isinstance(data, dict):
            raise InventoryPlanningResponseError(
                "Item da Inventory Planning API possui formato inválido."
            )
        return data

