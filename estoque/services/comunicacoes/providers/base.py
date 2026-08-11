from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ProviderResult:
    sucesso: bool
    provider_message_id: str = ''
    resposta: dict = field(default_factory=dict)
    erro: str = ''
    repetivel: bool = True


class WhatsAppProvider(Protocol):
    def enviar_payload(
        self,
        *,
        destino: str,
        payload: dict,
        idempotency_key: str,
    ) -> ProviderResult:
        ...

