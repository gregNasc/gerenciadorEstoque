from django.shortcuts import get_object_or_404
from .models import Equipamento, Historico, Base
from django.db.models import Count, Q, Sum, F
from django.db.models.functions import Coalesce
from datetime import date

def filtrar_por_empresa(queryset, request, campo_empresa='empresa'):
    empresa = getattr(request, 'empresa', None)

    if not empresa:
        return queryset.none()

    return queryset.filter(**{campo_empresa: empresa})


def get_object_empresa_or_404(model, request, campo_empresa='empresa', **kwargs):
    empresa = getattr(request, 'empresa', None)

    if not empresa:
        raise Exception("Usuário sem empresa")

    kwargs[campo_empresa] = empresa
    return get_object_or_404(model, **kwargs)


def qs_equipamentos(request):
    return filtrar_por_empresa(
        Equipamento.objects.select_related('produto', 'regional'),
        request,
        campo_empresa='regional__empresa'
    )


def qs_historico(request):
    qs = Historico.objects.select_related(
        'equipamento',
        'equipamento__produto',
        'usuario'
    )

    if request.user.is_superuser:
        return qs

    perfil = getattr(request.user, 'perfil', None)

    if not perfil:
        return qs.none()

    bases = perfil.bases.all()

    if not bases.exists():
        return qs.none()

    return qs.filter(equipamento__base__in=bases)


def qs_bases(request):
    return filtrar_por_empresa(
        Base.objects.all(),
        request
    )


class EstoqueService:
    STATUS_ATIVO = 'ATIVO'
    STATUS_SICK = 'SICK'
    STATUS_TRANSFERENCIA = 'TRANSFERENCIA'
    STATUS_MANUTENCAO = 'MANUTENCAO'
    STATUS_BAIXA = 'BAIXA'

    @classmethod
    def get_kpis_gerais(cls, queryset):
        return queryset.aggregate(
            total=Count('id'),
            ativos=Count('id', filter=Q(status=cls.STATUS_ATIVO)),
            sick=Count('id', filter=Q(status=cls.STATUS_SICK)),
            transferencia=Count('id', filter=Q(status=cls.STATUS_TRANSFERENCIA)),
            manutencao=Count('id', filter=Q(status=cls.STATUS_MANUTENCAO)),
            baixa=Count('id', filter=Q(status=cls.STATUS_BAIXA)),
        )

    @classmethod
    def get_disponibilidade(cls, queryset):
        kpis = cls.get_kpis_gerais(queryset)
        total = kpis['total'] or 0
        ativos = kpis['ativos'] or 0

        if total > 0:
            return round((ativos / total) * 100, 2)
        return 0

    @classmethod
    def get_kpis_por_regional(cls, queryset, regionais_lista):
        produtos_especificos = [
            {'nome': 'Coletores', 'filtro': 'Coletor'},
            {'nome': 'Impressoras', 'filtro': 'Impressora'},
            {'nome': 'Notebooks', 'filtro': 'Notebook'},
            {'nome': 'Routers', 'filtro': 'Router'},
        ]

        kpis_regionais = []

        for regional in regionais_lista:
            equip_regional = queryset.filter(regional=regional)

            kpis_regional = cls.get_kpis_gerais(equip_regional)

            regional_data = {
                'regional__id': regional.id,
                'regional__nome': regional.nome,
                'total': kpis_regional['total'],
                'ativos': kpis_regional['ativos'],  # Todos ATIVOS
                'sick': kpis_regional['sick'],  # Apenas SICK ativos
                'transferencia': kpis_regional['transferencia'],
                'manutencao': kpis_regional['manutencao'],
                'disponibilidade': cls.get_disponibilidade(equip_regional),
                'produtos': {}
            }

            for produto in produtos_especificos:
                equip_produto = equip_regional.filter(
                    Q(produto__descricao__icontains=produto['filtro']) |
                    Q(produto__descricao__icontains=produto['nome'])
                )

                produto_data = cls.get_kpis_gerais(equip_produto)

                produto_data['disponibilidade'] = cls.get_disponibilidade(equip_produto)

                regional_data['produtos'][produto['nome']] = produto_data

            kpis_regionais.append(regional_data)

        return kpis_regionais

    @classmethod
    def get_produtos_agrupados(cls, queryset):
        return (
            queryset
            .values(
                'produto__id',
                'produto__descricao',
                'regional__id',
                'regional__nome'
            )
            .annotate(
                total=Count('id'),
                ativos=Count('id', filter=Q(status=cls.STATUS_ATIVO)),
                sick=Count('id', filter=Q(status=cls.STATUS_SICK)),
                transferencia=Count('id', filter=Q(status=cls.STATUS_TRANSFERENCIA)),
                manutencao=Count('id', filter=Q(status=cls.STATUS_MANUTENCAO)),
            )
            .order_by('produto__descricao', 'regional__nome')
        )

    @classmethod
    def get_detalhes_completos_produto(cls, queryset, produto_id=None, regional_id=None):
        if produto_id:
            queryset = queryset.filter(produto_id=produto_id)
        if regional_id:
            queryset = queryset.filter(regional_id=regional_id)

        return queryset.values('status').annotate(
            total=Count('id')
        ).order_by('status')