from dataclasses import dataclass

from django.conf import settings

from integracao.models import TotvsIntegrationConfig
from integracao.totvs.registry import TotvsAdapterRegistry


@dataclass(frozen=True)
class TotvsReadinessResult:
    pronto: bool
    bloqueios: tuple[str, ...]


class TotvsReadinessService:
    @classmethod
    def avaliar(cls, config):
        bloqueios = []
        if not getattr(settings, 'TOTVS_ENABLED', False):
            bloqueios.append('TOTVS_ENABLED está desativado.')
        if config is None:
            bloqueios.append('A empresa não possui configuração TOTVS.')
            return TotvsReadinessResult(False, tuple(bloqueios))
        if not config.habilitada:
            bloqueios.append('A integração está desativada para a empresa.')
        if config.produto == TotvsIntegrationConfig.Produto.NAO_DEFINIDO:
            bloqueios.append('O produto TOTVS ainda não foi confirmado.')
        if not config.versao:
            bloqueios.append('A versão do produto ainda não foi confirmada.')
        if not config.modulos:
            bloqueios.append('Os módulos utilizados ainda não foram confirmados.')
        if not config.api_base_url:
            bloqueios.append('A URL oficial da API ainda não foi informada.')
        if (
            config.ambiente == TotvsIntegrationConfig.Ambiente.PRODUCAO
            and not getattr(settings, 'TOTVS_ALLOW_PRODUCTION', False)
        ):
            bloqueios.append('O envio para produção não foi liberado no ambiente.')
        if not TotvsAdapterRegistry.supports(config.produto):
            bloqueios.append('Não existe adaptador instalado para o produto confirmado.')
        return TotvsReadinessResult(not bloqueios, tuple(bloqueios))
