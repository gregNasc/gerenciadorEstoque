from .models import Perfil

class EmpresaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.empresa = None

        user = getattr(request, 'user', None)

        if user and user.is_authenticated:
            try:
                perfil = Perfil.objects.select_related('empresa').get(user=user)
                request.empresa = perfil.empresa
            except Perfil.DoesNotExist:
                pass

        return self.get_response(request)