from django.db.models import Exists, OuterRef
from .models import (
    Comunicado,
    ComunicadoLeitura
)

def notificacoes_context(request):

    if not request.user.is_authenticated:
        return {}

    lidos = ComunicadoLeitura.objects.filter(
        usuario=request.user,
        comunicado=OuterRef('pk')
    )

    comunicados_nao_lidos = (
        Comunicado.objects
        .filter(
            ativo=True
        )
        .annotate(
            lido=Exists(lidos)
        )
        .filter(
            lido=False
        )
        .count()
    )

    return {
        'comunicados_nao_lidos': comunicados_nao_lidos
    }