from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from functools import wraps

from estoque.models import Empresa
from estoque.tenant_policies import TenantAccessPolicy

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


def tenant_required(view_func):
    """Exige autenticação e um tenant fixo (ou escopo global de plataforma)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        TenantAccessPolicy.require_tenant(request)
        return view_func(request, *args, **kwargs)

    wrapper.tenant_protected = True
    return wrapper


def tenant_company_access(
    *,
    company_kwarg='empresa_id',
    manage=False,
    resource=None,
    action=None,
):
    """Protege uma view cujo URL identifica diretamente uma Empresa."""

    if bool(resource) != bool(action):
        raise ImproperlyConfigured(
            'resource e action devem ser informados em conjunto.'
        )

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            TenantAccessPolicy.require_tenant(request)
            if company_kwarg not in kwargs:
                raise ImproperlyConfigured(
                    f'O parâmetro de URL {company_kwarg!r} não foi recebido.'
                )
            company = get_object_or_404(Empresa, pk=kwargs[company_kwarg])
            TenantAccessPolicy.require_company_access(
                request,
                company,
                manage=manage,
                resource=resource,
                action=action,
            )
            request.tenant_company = company
            return view_func(request, *args, **kwargs)

        wrapper.tenant_protected = True
        wrapper.tenant_company_kwarg = company_kwarg
        wrapper.tenant_resource = resource
        wrapper.tenant_action = action
        return wrapper

    return decorator


def tenant_object_access(
    model,
    *,
    company_path,
    lookup_url_kwarg='pk',
    lookup_field='pk',
    manage=False,
    resource=None,
    action=None,
):
    """Carrega um objeto e bloqueia referências que cruzem a fronteira tenant."""

    if bool(resource) != bool(action):
        raise ImproperlyConfigured(
            'resource e action devem ser informados em conjunto.'
        )
    if not company_path:
        raise ImproperlyConfigured('company_path é obrigatório.')

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            TenantAccessPolicy.require_tenant(request)
            if lookup_url_kwarg not in kwargs:
                raise ImproperlyConfigured(
                    f'O parâmetro de URL {lookup_url_kwarg!r} não foi recebido.'
                )
            obj = get_object_or_404(
                model,
                **{lookup_field: kwargs[lookup_url_kwarg]},
            )
            TenantAccessPolicy.require_object_access(
                request,
                obj,
                company_path=company_path,
                manage=manage,
                resource=resource,
                action=action,
            )
            request.tenant_object = obj
            return view_func(request, *args, **kwargs)

        wrapper.tenant_protected = True
        wrapper.tenant_object_model = model
        wrapper.tenant_company_path = company_path
        wrapper.tenant_resource = resource
        wrapper.tenant_action = action
        return wrapper

    return decorator
