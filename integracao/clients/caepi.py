from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

import requests


class CaepiLookupStatus(StrEnum):
    FOUND = 'FOUND'
    NOT_FOUND = 'NOT_FOUND'
    UNAVAILABLE = 'UNAVAILABLE'


@dataclass(frozen=True, slots=True)
class CaepiLookupResult:
    status: CaepiLookupStatus
    numero_ca: str
    validade_ca: date | None = None
    fabricante_importador: str = ''
    produto: str = ''
    source: str = ''
    detail: str = ''
    situacao: str = ''
    natureza: str = ''
    descricao: str = ''
    marca: str = ''
    referencia: str = ''
    cor: str = ''
    aprovado_para: str = ''
    restricao: str = ''
    observacao_analise: str = ''
    numero_laudo: str = ''
    norma: str = ''
    catalogo_publicado_em: datetime | None = None
    ocorrencias: tuple = ()


class CaepiProvider(Protocol):
    """Contrato estável para um futuro provedor oficial de consulta CAEPI."""

    def consultar(self, numero_ca: str) -> CaepiLookupResult:
        ...


class CaepiDisabledProvider:
    """Provider seguro da primeira release: cadastro manual continua disponível."""

    def consultar(self, numero_ca: str) -> CaepiLookupResult:
        return CaepiLookupResult(
            status=CaepiLookupStatus.UNAVAILABLE,
            numero_ca=numero_ca,
            source='manual',
            detail=(''

            ),
        )


class CaepiDatabaseProvider:
    """Consulta somente a última versão CAEPI publicada no PostgreSQL."""

    def consultar(self, numero_ca: str) -> CaepiLookupResult:
        from integracao.models import CaepiImportacao

        catalogo = CaepiImportacao.objects.filter(
            status=CaepiImportacao.Status.PUBLICADA,
        ).first()
        if catalogo is None:
            return CaepiLookupResult(
                status=CaepiLookupStatus.UNAVAILABLE,
                numero_ca=numero_ca,
                source='caepi-local',
                detail='A base CAEPI ainda não foi publicada.',
            )
        registros = list(catalogo.registros.filter(numero_ca=numero_ca))
        if not registros:
            return CaepiLookupResult(
                status=CaepiLookupStatus.NOT_FOUND,
                numero_ca=numero_ca,
                source='caepi-local',
                detail='CA não localizado na última base CAEPI publicada.',
                catalogo_publicado_em=catalogo.publicado_em,
            )

        def unique(field):
            return tuple(dict.fromkeys(
                value for value in (getattr(item, field) for item in registros) if value
            ))

        validades = [item.validade_ca for item in registros if item.validade_ca]
        ocorrencias = tuple({
            'situacao': item.situacao,
            'validade_ca': item.validade_ca.isoformat() if item.validade_ca else '',
            'natureza': item.natureza,
            'equipamento': item.equipamento,
            'descricao': item.descricao_equipamento,
            'marca': item.marca,
            'referencia': item.referencia,
            'cor': item.cor,
            'aprovado_para': item.aprovado_para,
            'restricao': item.restricao,
            'observacao_analise': item.observacao_analise,
            'numero_laudo': item.numero_laudo,
            'norma': item.norma,
        } for item in registros)
        return CaepiLookupResult(
            status=CaepiLookupStatus.FOUND,
            numero_ca=numero_ca,
            validade_ca=max(validades) if validades else None,
            produto='; '.join(unique('equipamento')),
            source='caepi-local',
            detail='; '.join(unique('situacao')),
            situacao='; '.join(unique('situacao')),
            natureza='; '.join(unique('natureza')),
            descricao='; '.join(unique('descricao_equipamento')),
            marca='; '.join(unique('marca')),
            referencia='; '.join(unique('referencia')),
            cor='; '.join(unique('cor')),
            aprovado_para='; '.join(unique('aprovado_para')),
            restricao='; '.join(unique('restricao')),
            observacao_analise='; '.join(unique('observacao_analise')),
            numero_laudo='; '.join(unique('numero_laudo')),
            norma='; '.join(unique('norma')),
            catalogo_publicado_em=catalogo.publicado_em,
            ocorrencias=ocorrencias,
        )


class CaepiHttpProvider:
    """Cliente para uma API CAEPI compatível configurada pelo ambiente.

    O MTE não documenta atualmente uma API pública de consulta unitária. Este
    cliente permanece desacoplado para permitir a adoção de um endpoint oficial
    futuro ou de um espelho corporativo da base oficial, sem alterar o domínio.
    """

    def __init__(self, *, url, token='', timeout=8, session=None):
        self.url = (url or '').strip()
        self.token = (token or '').strip()
        self.timeout = timeout
        self.session = session or requests.Session()

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        raw = str(value).strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%dT%H:%M:%S'):
            try:
                return datetime.strptime(raw[:19], fmt).date()
            except ValueError:
                continue
        return None

    def consultar(self, numero_ca: str) -> CaepiLookupResult:
        if not self.url:
            return CaepiDisabledProvider().consultar(numero_ca)

        headers = {'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        try:
            response = self.session.get(
                self.url,
                params={'numero_ca': numero_ca},
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException:
            return CaepiLookupResult(
                status=CaepiLookupStatus.UNAVAILABLE,
                numero_ca=numero_ca,
                source='api-configurada',
                detail='Não foi possível acessar o serviço de consulta de CA.',
            )

        if response.status_code == 404:
            return CaepiLookupResult(
                status=CaepiLookupStatus.NOT_FOUND,
                numero_ca=numero_ca,
                source='api-configurada',
                detail='CA não localizado na fonte consultada.',
            )
        if response.status_code >= 400:
            return CaepiLookupResult(
                status=CaepiLookupStatus.UNAVAILABLE,
                numero_ca=numero_ca,
                source='api-configurada',
                detail='O serviço de consulta de CA está indisponível.',
            )

        try:
            payload = response.json()
        except ValueError:
            return CaepiLookupResult(
                status=CaepiLookupStatus.UNAVAILABLE,
                numero_ca=numero_ca,
                source='api-configurada',
                detail='O serviço de consulta retornou uma resposta inválida.',
            )

        if not isinstance(payload, dict):
            return CaepiLookupResult(
                status=CaepiLookupStatus.UNAVAILABLE,
                numero_ca=numero_ca,
                source='api-configurada',
                detail='O serviço de consulta retornou uma resposta inválida.',
            )
        data = payload.get('data', payload)
        if not isinstance(data, dict):
            return CaepiLookupResult(
                status=CaepiLookupStatus.UNAVAILABLE,
                numero_ca=numero_ca,
                source='api-configurada',
                detail='O serviço de consulta retornou uma resposta inválida.',
            )
        found = data.get('encontrado', data.get('found', True))
        if not found:
            return CaepiLookupResult(
                status=CaepiLookupStatus.NOT_FOUND,
                numero_ca=numero_ca,
                source='api-configurada',
                detail='CA não localizado na fonte consultada.',
            )

        numero_retornado = str(
            data.get('numero_ca')
            or data.get('numero')
            or data.get('NRRegistroCA')
            or numero_ca
        ).strip().upper()
        return CaepiLookupResult(
            status=CaepiLookupStatus.FOUND,
            numero_ca=numero_retornado,
            validade_ca=self._parse_date(
                data.get('validade_ca')
                or data.get('data_validade')
                or data.get('DataValidade')
            ),
            fabricante_importador=str(
                data.get('fabricante_importador')
                or data.get('razao_social')
                or data.get('RazaoSocial')
                or ''
            ).strip(),
            produto=str(
                data.get('produto')
                or data.get('equipamento')
                or data.get('NomeEquipamento')
                or ''
            ).strip(),
            source='api-configurada',
            detail=str(data.get('situacao') or data.get('Situacao') or '').strip(),
        )
