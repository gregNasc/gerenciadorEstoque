from django.http import HttpResponseForbidden

def role_required(*roles):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):

            if not request.user.is_authenticated:
                return HttpResponseForbidden("Usuário não autenticado")

            perfil = getattr(request.user, 'perfil', None)

            if not perfil:
                return HttpResponseForbidden("Usuário sem perfil cadastrado. Contate o administrador.")

            if perfil.role not in roles:
                return HttpResponseForbidden("Sem permissão")

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator

def regional_required(view_func):
    def wrapper(request, *args, **kwargs):
        perfil = request.user.perfil

        if not perfil.regional and not perfil.is_admin():
            return HttpResponseForbidden("Sem acesso à regional")

        return view_func(request, *args, **kwargs)
    return wrapper