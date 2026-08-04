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
    def enviar_template(
        self,
        *,
        destino: str,
        template_codigo: str,
        idioma: str,
        parametros: dict,
        idempotency_key: str,
    ) -> ProviderResult:
        ...

