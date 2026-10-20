from integracao.clients.caepi import (
    CaepiDatabaseProvider,
    CaepiLookupResult,
    CaepiProvider,
)
from insumos.services.certificado_epi_service import CertificadoEpiService


class CaepiService:
    """Orquestra a consulta sem acoplar o domínio EPI a uma API externa."""

    def __init__(self, provider: CaepiProvider | None = None):
        self.provider = provider or self._provider_from_settings()

    @staticmethod
    def _provider_from_settings():
        return CaepiDatabaseProvider()

    def consultar(self, numero_ca: str) -> CaepiLookupResult:
        numero_normalizado = CertificadoEpiService.normalizar_numero(numero_ca)
        if not numero_normalizado:
            raise ValueError('Informe o número do CA para realizar a consulta.')
        resultado = self.provider.consultar(numero_normalizado)
        if resultado.numero_ca != numero_normalizado:
            raise ValueError('O provedor retornou dados de outro número de CA.')
        return resultado
