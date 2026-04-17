from .models import Perfil
from django.db import DatabaseError

class EmpresaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.empresa = None

        user = getattr(request, 'user', None)

        if user and user.is_authenticated:
            try:
                perfil = (
                    Perfil.objects
                    .select_related('empresa')
                    .filter(user=user)
                    .first()
                )

                if perfil:
                    request.empresa = perfil.empresa

            except DatabaseError:
                # evita crash em cold start ou falha de conexão
                request.empresa = None

        return self.get_response(request)