from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

from django.core.exceptions import PermissionDenied
from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from insumos.models import (
    ConsumoInsumo,
    Insumo,
    ItemSolicitacaoInsumo,
    SaldoInsumoBase,
    SolicitacaoInsumo,
)
from insumos.policies import InsumosTenantPolicy


CAMPO_QUANTIDADE = DecimalField(max_digits=18, decimal_places=2)


class IndicadoresPlanejamentoService:
    """Indicadores operacionais R8 sem preços, custos ou decisões automáticas."""

    STATUS_ABERTOS = (
        'PENDENTE',
        'RECEBIDA_COMPRAS',
        'EM_ANALISE',
        'APROVADA',
        'EM_COMPRA',
        'PEDIDO_REALIZADO',
        'RECEBIDA',
    )

    @staticmethod
    def pode_visualizar(user):
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        perfil = getattr(user, 'perfil', None)
        return bool(
            perfil
            and (
                perfil.is_admin
                or perfil.is_compras_insumos
                or perfil.is_planejamento_insumos
                or perfil.is_executivo_insumos
            )
        )

    @classmethod
    def bases_permitidas(cls, user, *, empresa_id=None, base_id=None):
        if not cls.pode_visualizar(user):
            raise PermissionDenied('Sem permissão para visualizar os indicadores.')
        bases = InsumosTenantPolicy.bases(user).filter(empresa__ativa=True)
        if empresa_id:
            if not bases.filter(empresa_id=empresa_id).exists():
                raise PermissionDenied('Empresa fora do escopo permitido.')
            bases = bases.filter(empresa_id=empresa_id)
        if base_id:
            if not bases.filter(pk=base_id).exists():
                raise PermissionDenied('Base fora do escopo permitido.')
            bases = bases.filter(pk=base_id)
        return bases

    @staticmethod
    def _zero(valor):
        return valor or Decimal('0')

    @staticmethod
    def _arredondar(valor):
        return Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @staticmethod
    def _limites_data(inicio, fim):
        inicio_dt = timezone.make_aware(datetime.combine(inicio, time.min))
        fim_exclusivo = timezone.make_aware(
            datetime.combine(fim + timedelta(days=1), time.min)
        )
        return inicio_dt, fim_exclusivo

    @classmethod
    def gerar(
        cls, *, user, empresa_id=None, base_id=None, inicio=None, fim=None,
    ):
        fim = fim or timezone.localdate()
        inicio = inicio or (fim - timedelta(days=364))
        if inicio > fim:
            raise ValueError('A data inicial não pode ser posterior à data final.')

        bases = cls.bases_permitidas(
            user, empresa_id=empresa_id, base_id=base_id,
        )
        bases_ids = list(bases.values_list('pk', flat=True))
        inicio_dt, fim_exclusivo = cls._limites_data(inicio, fim)
        dias_periodo = max((fim - inicio).days + 1, 1)
        marco_recente = max(inicio_dt, fim_exclusivo - timedelta(days=90))
        marco_anterior = max(inicio_dt, marco_recente - timedelta(days=90))

        itens = (
            ItemSolicitacaoInsumo.objects
            .filter(
                solicitacao__base_id__in=bases_ids,
                solicitacao__criado_em__gte=inicio_dt,
                solicitacao__criado_em__lt=fim_exclusivo,
            )
            .filter(Q(insumo_id__isnull=False) | Q(resolvido_insumo_id__isnull=False))
            .annotate(
                indicador_insumo_id=Coalesce('insumo_id', 'resolvido_insumo_id')
            )
        )
        solicitacoes_por_item = list(
            itens.values('indicador_insumo_id').annotate(
                quantidade_solicitada=Coalesce(
                    Sum('quantidade'), Value(Decimal('0')),
                    output_field=CAMPO_QUANTIDADE,
                ),
                quantidade_atendida=Coalesce(
                    Sum('quantidade_atendida'), Value(Decimal('0')),
                    output_field=CAMPO_QUANTIDADE,
                ),
                total_solicitacoes=Count('solicitacao_id', distinct=True),
                solicitacoes_abertas=Count(
                    'solicitacao_id',
                    filter=Q(solicitacao__status__in=cls.STATUS_ABERTOS),
                    distinct=True,
                ),
                ultima_solicitacao=Max('solicitacao__criado_em'),
            )
        )

        # ``bases_ids`` já foi produzido pelo queryset protegido da policy.
        # Reutilizá-lo evita recalcular o mesmo escopo para cada fonte.
        consumos_por_item = list(
            ConsumoInsumo.objects.filter(
                inventario__base_id__in=bases_ids,
                criado_em__gte=inicio_dt,
                criado_em__lt=fim_exclusivo,
            )
            .values('insumo_id')
            .annotate(
                quantidade_consumida=Coalesce(
                    Sum('quantidade'), Value(Decimal('0')),
                    output_field=CAMPO_QUANTIDADE,
                ),
                consumo_recente=Coalesce(
                    Sum('quantidade', filter=Q(criado_em__gte=marco_recente)),
                    Value(Decimal('0')), output_field=CAMPO_QUANTIDADE,
                ),
                consumo_anterior=Coalesce(
                    Sum('quantidade', filter=Q(
                        criado_em__gte=marco_anterior,
                        criado_em__lt=marco_recente,
                    )),
                    Value(Decimal('0')), output_field=CAMPO_QUANTIDADE,
                ),
            )
        )

        saldos_por_item = list(
            SaldoInsumoBase.objects.filter(base_id__in=bases_ids)
            .values('insumo_id')
            .annotate(
                estoque_atual=Coalesce(
                    Sum('saldo'), Value(Decimal('0')),
                    output_field=CAMPO_QUANTIDADE,
                ),
                estoque_reservado=Coalesce(
                    Sum('saldo_reservado'), Value(Decimal('0')),
                    output_field=CAMPO_QUANTIDADE,
                ),
            )
        )

        quantidades = defaultdict(list)
        datas = defaultdict(set)
        for insumo_id, quantidade, criado_em in itens.values_list(
            'indicador_insumo_id', 'quantidade', 'solicitacao__criado_em'
        ).iterator():
            quantidades[insumo_id].append(quantidade)
            datas[insumo_id].add(criado_em.date())

        por_insumo = defaultdict(dict)
        for linha in solicitacoes_por_item:
            por_insumo[linha.pop('indicador_insumo_id')].update(linha)
        for linha in consumos_por_item:
            por_insumo[linha.pop('insumo_id')].update(linha)
        for linha in saldos_por_item:
            por_insumo[linha.pop('insumo_id')].update(linha)

        catalogo = (
            Insumo.objects.filter(pk__in=por_insumo)
            .select_related('categoria')
            .in_bulk()
        )
        resultados = []
        for insumo_id, dados in por_insumo.items():
            insumo = catalogo.get(insumo_id)
            if not insumo:
                continue
            solicitado = cls._zero(dados.get('quantidade_solicitada'))
            atendido = cls._zero(dados.get('quantidade_atendida'))
            consumido = cls._zero(dados.get('quantidade_consumida'))
            estoque = cls._zero(dados.get('estoque_atual'))
            reservado = cls._zero(dados.get('estoque_reservado'))
            disponivel = max(estoque - reservado, Decimal('0'))
            base_demanda = consumido if consumido > 0 else atendido
            fonte_demanda = 'Consumo' if consumido > 0 else 'Atendimento'
            demanda_anual = cls._arredondar(
                base_demanda * Decimal(365) / Decimal(dias_periodo)
            )

            datas_item = sorted(datas.get(insumo_id, set()))
            intervalos = [
                (atual - anterior).days
                for anterior, atual in zip(datas_item, datas_item[1:])
            ]
            intervalo_tipico = int(median(intervalos)) if intervalos else None
            quantidade_usual = (
                cls._arredondar(median(quantidades[insumo_id]))
                if quantidades.get(insumo_id) else Decimal('0')
            )
            consumo_recente = cls._zero(dados.get('consumo_recente'))
            consumo_anterior = cls._zero(dados.get('consumo_anterior'))
            if consumo_recente > consumo_anterior:
                tendencia = 'Alta'
                tendencia_classe = 'atencao'
            elif consumo_recente < consumo_anterior:
                tendencia = 'Baixa'
                tendencia_classe = 'ok'
            else:
                tendencia = 'Estável'
                tendencia_classe = 'neutro'

            cobertura_dias = None
            sugestao_quantidade = Decimal('0')
            if demanda_anual > 0:
                cobertura_dias = cls._arredondar(
                    disponivel * Decimal(365) / demanda_anual
                )
                necessidade_30_dias = demanda_anual * Decimal(30) / Decimal(365)
                sugestao_quantidade = cls._arredondar(
                    max(necessidade_30_dias - disponivel, Decimal('0'))
                )

            abertas = dados.get('solicitacoes_abertas', 0)
            if disponivel <= 0 and abertas:
                sugestao = 'Sem estoque e com solicitação aberta. Avalie reposição prioritária.'
                nivel = 'CRITICO'
            elif sugestao_quantidade > 0:
                sugestao = 'Cobertura inferior a 30 dias. Avalie reposição.'
                nivel = 'ATENCAO'
            elif demanda_anual <= 0:
                sugestao = 'Histórico insuficiente para sugerir reposição.'
                nivel = 'NEUTRO'
            else:
                sugestao = 'Estoque compatível com a demanda observada.'
                nivel = 'OK'

            resultados.append({
                'insumo_id': insumo_id,
                'insumo': insumo.descricao,
                'categoria': insumo.categoria.nome,
                'unidade': insumo.unidade_medida,
                'quantidade_solicitada': solicitado,
                'quantidade_atendida': atendido,
                'quantidade_consumida': consumido,
                'estoque_atual': estoque,
                'estoque_reservado': reservado,
                'estoque_disponivel': disponivel,
                'total_solicitacoes': dados.get('total_solicitacoes', 0),
                'solicitacoes_abertas': abertas,
                'ultima_solicitacao': dados.get('ultima_solicitacao'),
                'quantidade_usual': quantidade_usual,
                'intervalo_tipico_dias': intervalo_tipico,
                'demanda_anual_estimada': demanda_anual,
                'fonte_demanda': fonte_demanda,
                'tendencia': tendencia,
                'tendencia_classe': tendencia_classe,
                'cobertura_dias': cobertura_dias,
                'sugestao_quantidade': sugestao_quantidade,
                'sugestao': sugestao,
                'nivel': nivel,
            })

        resultados.sort(key=lambda item: (
            {'CRITICO': 0, 'ATENCAO': 1, 'OK': 2, 'NEUTRO': 3}[item['nivel']],
            item['insumo'].casefold(),
        ))
        solicitacoes_abertas = (
            SolicitacaoInsumo.objects
            .filter(base_id__in=bases_ids, status__in=cls.STATUS_ABERTOS)
            .count()
        )
        return {
            'inicio': inicio,
            'fim': fim,
            'dias_periodo': dias_periodo,
            'bases_ids': bases_ids,
            'itens': resultados,
            'totais': {
                'itens_monitorados': len(resultados),
                'solicitacoes_abertas': solicitacoes_abertas,
                'itens_criticos': sum(
                    item['nivel'] == 'CRITICO' for item in resultados
                ),
                'itens_para_avaliar': sum(
                    item['nivel'] in {'CRITICO', 'ATENCAO'} for item in resultados
                ),
            },
        }
