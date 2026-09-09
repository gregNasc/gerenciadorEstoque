from django.db.models import Count
from estoque.models import Equipamento, Produto
from estoque.security import secure_queryset

def get_estoque_por_produto(user):
    estoque = (
        secure_queryset(Equipamento.objects.all(), user)
        .filter(status='ATIVO', finalidade=Equipamento.Finalidade.OPERACIONAL)
        .values(
            'produto_id',
            'produto__descricao',
            'produto__categoria',
            'regional_id',
            'regional__nome'
        )
        .annotate(total=Count('id'))
    )

    mapa = {}

    for e in estoque:
        pid = e['produto_id']

        mapa.setdefault(pid, {
            'produto': e['produto__descricao'],
            'categoria': e['produto__categoria'],
            'regionais': []
        })

        mapa[pid]['regionais'].append({
            'regional_id': e['regional_id'],
            'regional': e['regional__nome'],
            'total': e['total']
        })

    return mapa
