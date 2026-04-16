from django.shortcuts import renderfrom
from models import Solicitacao

@login_required
def criar_solicitacao(request):

    if not is_gestor(request.user):
        return JsonResponse({'erro': 'Sem permissão'}, status=403)

    produto_id = request.POST.get('produto')
    quantidade = request.POST.get('quantidade')

    solicitacao = Solicitacao.objects.create(
        solicitante=request.user,
        regional_solicitante=request.user.perfil.regionais.first(),
        produto_id=produto_id,
        quantidade=quantidade
    )

    return JsonResponse({'sucesso': True})