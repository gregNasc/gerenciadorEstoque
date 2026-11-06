from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TotvsAdapterResult:
    referencia_remota: str
    status_remoto: str
    confirmado: bool = False
    http_status: int | None = None
    requisicao_sha256: str = ''
    resposta_sha256: str = ''


class TotvsAdapter(ABC):
    """Contrato implementado somente após produto e API serem confirmados."""

    @abstractmethod
    def enviar(self, *, config, operacao) -> TotvsAdapterResult:
        raise NotImplementedError

    @abstractmethod
    def reconciliar(self, *, config, operacao) -> TotvsAdapterResult:
        raise NotImplementedError
