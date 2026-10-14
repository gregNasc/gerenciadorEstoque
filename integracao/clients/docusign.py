import base64
import json
import logging
import re
import time
from urllib.parse import quote, urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings
from django.core.cache import cache

from integracao.exceptions import (
    DocusignAuthenticationError,
    DocusignConfigurationError,
    DocusignResponseError,
    DocusignTransportError,
)


logger = logging.getLogger('integracao.docusign')


class DocusignClient:
    RETRYABLE_STATUS = {429, 500, 502, 503, 504}
    ACCOUNT_ID_PATTERN = re.compile(r'^[A-Za-z0-9-]+$')

    def __init__(
        self,
        *,
        enabled=None,
        auth_server=None,
        esign_base_url=None,
        integration_key=None,
        user_id=None,
        private_key=None,
        timeout=None,
        max_retries=None,
        backoff_base=None,
        http_client=None,
        sleep=None,
    ):
        self.enabled = settings.DOCUSIGN_ENABLED if enabled is None else enabled
        self.auth_server = (
            auth_server or settings.DOCUSIGN_AUTH_SERVER
        ).rstrip('/')
        self.esign_base_url = (
            esign_base_url or settings.DOCUSIGN_ESIGN_BASE_URL
        ).rstrip('/')
        self.integration_key = (
            integration_key or settings.DOCUSIGN_INTEGRATION_KEY
        )
        self.user_id = user_id or settings.DOCUSIGN_USER_ID
        self.private_key = private_key or settings.DOCUSIGN_PRIVATE_KEY
        self.timeout = timeout if timeout is not None else settings.DOCUSIGN_TIMEOUT
        self.max_retries = (
            max_retries
            if max_retries is not None else settings.DOCUSIGN_MAX_RETRIES
        )
        self.backoff_base = (
            backoff_base
            if backoff_base is not None else settings.DOCUSIGN_BACKOFF_BASE
        )
        self._sleep = sleep or time.sleep
        self._validate_configuration()
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=False,
            verify=True,
        )
        self._owns_client = http_client is None

    def _validate_configuration(self):
        if not self.enabled:
            raise DocusignConfigurationError(
                'A integração DocuSign está desabilitada.'
            )
        for value, setting_name in (
            (self.auth_server, 'DOCUSIGN_AUTH_SERVER'),
            (self.esign_base_url, 'DOCUSIGN_ESIGN_BASE_URL'),
        ):
            parsed = urlparse(value)
            if parsed.scheme != 'https' or not parsed.netloc:
                raise DocusignConfigurationError(
                    f'{setting_name} deve ser uma URL HTTPS válida.'
                )
        missing = [
            name for value, name in (
                (self.integration_key, 'DOCUSIGN_INTEGRATION_KEY'),
                (self.user_id, 'DOCUSIGN_USER_ID'),
                (self.private_key, 'DOCUSIGN_PRIVATE_KEY'),
            ) if not value
        ]
        if missing:
            raise DocusignConfigurationError(
                f'Configuração DocuSign incompleta: {", ".join(missing)}.'
            )
        if self.timeout <= 0 or self.max_retries < 0 or self.backoff_base < 0:
            raise DocusignConfigurationError(
                'Timeout e política de tentativas DocuSign são inválidos.'
            )

    def close(self):
        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @staticmethod
    def _b64url(value):
        return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')

    def _jwt_assertion(self):
        now = int(time.time())
        header = self._b64url(json.dumps(
            {'alg': 'RS256', 'typ': 'JWT'},
            separators=(',', ':'),
        ).encode())
        payload = self._b64url(json.dumps(
            {
                'iss': self.integration_key,
                'sub': self.user_id,
                'aud': urlparse(self.auth_server).netloc,
                'iat': now - 30,
                'exp': now + 3600,
                'scope': 'signature impersonation',
            },
            separators=(',', ':'),
        ).encode())
        unsigned = f'{header}.{payload}'.encode('ascii')
        try:
            key = serialization.load_pem_private_key(
                self.private_key.encode(), password=None,
            )
            signature = key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
        except (TypeError, ValueError) as exc:
            raise DocusignConfigurationError(
                'DOCUSIGN_PRIVATE_KEY não contém uma chave RSA PEM válida.'
            ) from exc
        return f'{header}.{payload}.{self._b64url(signature)}'

    def _access_token(self):
        cache_key = f'docusign:jwt:{self.integration_key}:{self.user_id}'
        cached = cache.get(cache_key)
        if cached:
            return cached
        try:
            response = self._client.post(
                f'{self.auth_server}/oauth/token',
                data={
                    'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                    'assertion': self._jwt_assertion(),
                },
                headers={'Accept': 'application/json'},
                timeout=self.timeout,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise DocusignTransportError(
                'Falha de transporte na autenticação DocuSign.'
            ) from exc
        if response.status_code in (400, 401, 403):
            raise DocusignAuthenticationError(
                'Autenticação DocuSign recusada; valide consentimento e secrets.'
            )
        if response.status_code >= 400 or response.is_redirect:
            raise DocusignResponseError(
                f'DocuSign recusou a autenticação ({response.status_code}).'
            )
        try:
            data = response.json()
            token = data['access_token']
            expires_in = int(data.get('expires_in', 3600))
        except (ValueError, KeyError, TypeError) as exc:
            raise DocusignResponseError(
                'DocuSign retornou autenticação inválida.'
            ) from exc
        cache.set(cache_key, token, max(60, expires_in - 300))
        return token

    def _account_url(self, account_id, suffix):
        if not self.ACCOUNT_ID_PATTERN.fullmatch(account_id or ''):
            raise DocusignConfigurationError('ID de conta DocuSign inválido.')
        safe_account = quote(account_id, safe='')
        return (
            f'{self.esign_base_url}/v2.1/accounts/{safe_account}/'
            f'{suffix.lstrip("/")}'
        )

    def _request(self, method, url, *, json_payload=None, accept='application/json'):
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(
                    method,
                    url,
                    json=json_payload,
                    headers={
                        'Authorization': f'Bearer {self._access_token()}',
                        'Accept': accept,
                        'Content-Type': 'application/json',
                    },
                    timeout=self.timeout,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self.max_retries:
                    raise DocusignTransportError(
                        'Falha de transporte ao acessar DocuSign.'
                    ) from exc
                self._sleep(self.backoff_base * (2 ** attempt))
                continue
            if response.status_code in self.RETRYABLE_STATUS:
                if attempt >= self.max_retries:
                    raise DocusignResponseError(
                        f'DocuSign indisponível ({response.status_code}).'
                    )
                self._sleep(self.backoff_base * (2 ** attempt))
                continue
            if response.status_code in (401, 403):
                raise DocusignAuthenticationError(
                    f'DocuSign recusou a requisição ({response.status_code}).'
                )
            if response.is_redirect or response.status_code >= 400:
                raise DocusignResponseError(
                    f'DocuSign recusou a requisição ({response.status_code}).'
                )
            return response
        raise DocusignTransportError('Falha inesperada ao acessar DocuSign.')

    def create_envelope(self, *, account_id, payload):
        response = self._request(
            'POST', self._account_url(account_id, 'envelopes'),
            json_payload=payload,
        )
        try:
            data = response.json()
            envelope_id = str(data['envelopeId']).strip()
        except (ValueError, KeyError, TypeError) as exc:
            raise DocusignResponseError(
                'DocuSign não retornou um envelope válido.'
            ) from exc
        if not envelope_id:
            raise DocusignResponseError('DocuSign retornou envelope vazio.')
        return data

    def download_document(self, *, account_id, envelope_id, document_id):
        if not self.ACCOUNT_ID_PATTERN.fullmatch(envelope_id or ''):
            raise DocusignResponseError('ID de envelope DocuSign inválido.')
        safe_envelope = quote(envelope_id, safe='')
        safe_document = quote(document_id, safe='')
        response = self._request(
            'GET',
            self._account_url(
                account_id,
                f'envelopes/{safe_envelope}/documents/{safe_document}',
            ),
            accept='application/pdf',
        )
        content = response.content
        if not content.startswith(b'%PDF-'):
            raise DocusignResponseError(
                'DocuSign retornou um documento concluído inválido.'
            )
        return content
