from functools import wraps

from django.core.exceptions import PermissionDenied
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render

from auditorias.services.visibilidade_estoque_service import VisibilidadeEstoqueAuditoriaService
from estoque.models import Base, Equipamento
from estoque.policies.compras import ComprasAccessPolicy
from insumos.models import SaldoInsumoBase


def pode_visualizar_saude_estoque(user):
    if not user or not user.is_authenticated or ComprasAccessPolicy.restrito(user):
        return False
    perfil = getattr(user, 'perfil', None)
    return bool(
        user.is_superuser
        or (perfil and (perfil.is_admin or perfil.is_executivo_insumos))
    )


def saude_estoque_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not pode_visualizar_saude_estoque(request.user):
            raise PermissionDenied('Sem permissão para visualizar a saúde do estoque.')
        return view(request, *args, **kwargs)
    return wrapper


def _equipamentos_visiveis(request):
    qs = Equipamento.objects.select_related('produto', 'regional__empresa')
    qs = VisibilidadeEstoqueAuditoriaService.ocultar_equipamentos(qs)
    empresa_id = request.GET.get('empresa')
    base_id = request.GET.get('base')
    if empresa_id and empresa_id.isdigit():
        qs = qs.filter(regional__empresa_id=empresa_id)
    if base_id and base_id.isdigit():
        qs = qs.filter(regional_id=base_id)
    return qs


def _filtros():
    return {
        'empresas': Base.objects.values('empresa_id', 'empresa__nome').distinct().order_by('empresa__nome'),
        'bases': Base.objects.select_related('empresa').order_by('empresa__nome', 'nome'),
    }


@saude_estoque_required
def dashboard_saude_equipamentos(request):
    qs = _equipamentos_visiveis(request)
    por_status = list(qs.values('status').annotate(total=Count('id')).order_by('-total'))
    labels_status = dict(Equipamento.STATUS_CHOICES)
    for item in por_status:
        item['label'] = str(labels_status.get(item['status'], item['status']))
    por_categoria = list(
        qs.values('produto__categoria').annotate(total=Count('id')).order_by('-total')
    )
    por_base = list(
        qs.values('regional__nome', 'regional__empresa__nome')
        .annotate(total=Count('id')).order_by('-total')[:12]
    )
    contexto = {
        **_filtros(),
        'total': qs.count(),
        'operacionais': qs.filter(status__in=['ATIVO', 'EM_USO', 'EMPRESTADO']).count(),
        'indisponiveis': qs.filter(status__in=['SICK', 'MANUTENCAO']).count(),
        'inativos': qs.filter(status__in=['INATIVO', 'BAIXA']).count(),
        'por_status': por_status,
        'por_categoria': por_categoria,
        'por_base': por_base,
        'grafico_status': {
            'labels': [item['label'] for item in por_status],
            'valores': [item['total'] for item in por_status],
        },
        'grafico_categoria': {
            'labels': [item['produto__categoria'] or 'Sem categoria' for item in por_categoria],
            'valores': [item['total'] for item in por_categoria],
        },
        'filtro_empresa_id': request.GET.get('empresa', ''),
        'filtro_base_id': request.GET.get('base', ''),
    }
    return render(request, 'insumos/dashboard/saude/saude_equipamentos.html', contexto)


@saude_estoque_required
def dashboard_saude_geral(request):
    equipamentos = _equipamentos_visiveis(request)
    saldos = SaldoInsumoBase.objects.select_related('base__empresa', 'insumo')
    empresa_id = request.GET.get('empresa')
    base_id = request.GET.get('base')
    if empresa_id and empresa_id.isdigit():
        saldos = saldos.filter(base__empresa_id=empresa_id)
    if base_id and base_id.isdigit():
        saldos = saldos.filter(base_id=base_id)

    valor_expr = ExpressionWrapper(
        F('saldo') * F('custo_medio'),
        output_field=DecimalField(max_digits=20, decimal_places=2),
    )
    por_base_equip = {
        row['regional_id']: row['total']
        for row in equipamentos.values('regional_id').annotate(total=Count('id'))
    }
    por_base_insumo = {
        row['base_id']: row['total']
        for row in saldos.values('base_id').annotate(total=Sum('saldo'))
    }
    bases = list(Base.objects.select_related('empresa').order_by('nome'))
    if empresa_id and empresa_id.isdigit():
        bases = [base for base in bases if base.empresa_id == int(empresa_id)]
    if base_id and base_id.isdigit():
        bases = [base for base in bases if base.id == int(base_id)]

    ranking = sorted(({
        'base': base.nome,
        'empresa': base.empresa.nome,
        'equipamentos': por_base_equip.get(base.id, 0),
        'insumos': float(por_base_insumo.get(base.id, 0)),
    } for base in bases), key=lambda row: row['equipamentos'] + row['insumos'], reverse=True)[:12]

    por_status = list(equipamentos.values('status').annotate(total=Count('id')).order_by('-total'))
    status_labels = dict(Equipamento.STATUS_CHOICES)
    contexto = {
        **_filtros(),
        'total_equipamentos': equipamentos.count(),
        'total_insumos': saldos.aggregate(
            total=Coalesce(Sum('saldo'), Value(Decimal('0')))
        )['total'],
        'itens_criticos': saldos.filter(saldo__lte=F('insumo__estoque_minimo')).count(),
        'valor_estoque': saldos.aggregate(
            total=Coalesce(Sum(valor_expr), Value(Decimal('0')))
        )['total'],
        'ranking': ranking,
        'grafico_status': {
            'labels': [str(status_labels.get(item['status'], item['status'])) for item in por_status],
            'valores': [item['total'] for item in por_status],
        },
        'grafico_bases': {
            'labels': [row['base'] for row in ranking],
            'equipamentos': [row['equipamentos'] for row in ranking],
            'insumos': [row['insumos'] for row in ranking],
        },
        'filtro_empresa_id': request.GET.get('empresa', ''),
        'filtro_base_id': request.GET.get('base', ''),
    }
    return render(request, 'insumos/dashboard/saude/saude_geral.html', contexto)
