from django.http import HttpResponseForbidden
from functools import wraps

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


def permission_or_role_required(permission, *roles):
    """Preserva os papéis-base e permite complementação por permissão Django."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return HttpResponseForbidden('Usuário não autenticado')
            perfil = getattr(request.user, 'perfil', None)
            if not perfil:
                return HttpResponseForbidden('Usuário sem perfil cadastrado. Contate o administrador.')
            if perfil.role not in roles and not request.user.has_perm(permission):
                return HttpResponseForbidden('Sem permissão')
            return view_func(request, *args, **kwargs)
        wrapper.required_operational_permission = permission
        return wrapper
    return decorator

def regional_required(view_func):
    def wrapper(request, *args, **kwargs):
        perfil = request.user.perfil

        if not perfil.regional and not perfil.is_admin():
            return HttpResponseForbidden("Sem acesso à regional")

        return view_func(request, *args, **kwargs)
    return wrapper
