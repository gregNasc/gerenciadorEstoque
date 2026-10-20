from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class EstadoEpi:
    codigo: str
    dias_restantes: int | None = None
    faixa_dias: int | None = None


class AlertaEpiService:
    FAIXAS = (30, 60, 90)

    CA_VALIDO = 'CA_VALIDO'
    CA_PROXIMO = 'CA_PROXIMO'
    CA_VENCIDO = 'CA_VENCIDO'
    CA_DIVERGENTE = 'CA_DIVERGENTE'
    CA_INEXISTENTE = 'CA_INEXISTENTE'
    VALIDADE_FISICA_VALIDA = 'VALIDADE_FISICA_VALIDA'
    VALIDADE_FISICA_PROXIMA = 'VALIDADE_FISICA_PROXIMA'
    EPI_VENCIDO = 'EPI_VENCIDO'
    SEM_VALIDADE_FISICA = 'SEM_VALIDADE_FISICA'

    @classmethod
    def _faixa(cls, dias_restantes):
        return next((faixa for faixa in cls.FAIXAS if dias_restantes <= faixa), None)

    @classmethod
    def estado_ca(cls, *, produto_epi=None, lote=None, referencia=None):
        referencia = referencia or date.today()
        certificado = getattr(lote, 'certificado', None) if lote is not None else None
        if lote is not None and lote.certificado_id:
            if certificado.produto_epi_id != lote.produto_epi_id:
                return EstadoEpi(cls.CA_DIVERGENTE)
        elif produto_epi is not None:
            certificado = produto_epi.certificados.filter(ativo=True).order_by(
                '-validade_ca', '-atualizado_em',
            ).first()

        if certificado is None:
            return EstadoEpi(cls.CA_INEXISTENTE)
        return cls.estado_certificado(
            certificado=certificado,
            referencia=referencia,
        )

    @classmethod
    def estado_certificado(cls, *, certificado, referencia=None):
        referencia = referencia or date.today()
        if certificado.validade_ca is None:
            return EstadoEpi(cls.CA_VALIDO)

        dias = (certificado.validade_ca - referencia).days
        if dias < 0:
            return EstadoEpi(cls.CA_VENCIDO, dias_restantes=dias)
        faixa = cls._faixa(dias)
        if faixa is not None:
            return EstadoEpi(cls.CA_PROXIMO, dias_restantes=dias, faixa_dias=faixa)
        return EstadoEpi(cls.CA_VALIDO, dias_restantes=dias)

    @classmethod
    def estado_validade_fisica(cls, *, lote, referencia=None):
        referencia = referencia or date.today()
        if lote.validade_fisica is None:
            return EstadoEpi(cls.SEM_VALIDADE_FISICA)
        dias = (lote.validade_fisica - referencia).days
        if dias < 0:
            return EstadoEpi(cls.EPI_VENCIDO, dias_restantes=dias)
        faixa = cls._faixa(dias)
        if faixa is not None:
            return EstadoEpi(
                cls.VALIDADE_FISICA_PROXIMA,
                dias_restantes=dias,
                faixa_dias=faixa,
            )
        return EstadoEpi(cls.VALIDADE_FISICA_VALIDA, dias_restantes=dias)
