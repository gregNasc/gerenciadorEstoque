from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

from estoque.tenant_scope import TenantScope


class TenantAccessPolicy:
    """Decisões reutilizáveis da fronteira entre tenants.

    Esta policy não substitui permissões funcionais do domínio. Ela responde
    somente se a requisição pode alcançar a empresa (ou um objeto dela).
    """

    AUTHENTICATION_MESSAGE = 'Usuário não autenticado.'
    TENANT_REQUIRED_MESSAGE = 'Usuário sem empresa definida para esta operação.'
    ACCESS_DENIED_MESSAGE = 'Sem acesso a esta empresa.'

    @classmethod
    def scope_for_request(cls, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return TenantScope.empty()

        scope = getattr(request, 'tenant_scope', None)
        if isinstance(scope, TenantScope) and scope.user_id == user.pk:
            return scope

        # Não confia em um escopo ausente, adulterado ou de outra identidade.
        return TenantScope.for_user(user)

    @classmethod
    def require_tenant(cls, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            raise PermissionDenied(cls.AUTHENTICATION_MESSAGE)

        scope = cls.scope_for_request(request)
        if not scope.is_platform_scope and not scope.has_fixed_tenant:
            raise PermissionDenied(cls.TENANT_REQUIRED_MESSAGE)
        return scope

    @classmethod
    def can_access_company(
        cls,
        request,
        company,
        *,
        manage=False,
        resource=None,
        action=None,
    ):
        scope = cls.scope_for_request(request)
        company_id = scope._company_id(company)
        if company_id is None:
            return False

        if scope.is_platform_scope:
            return True
        if not scope.has_fixed_tenant:
            return False

        # A company principal já está dentro da fronteira tenant. A permissão
        # funcional da ação continua sendo responsabilidade da policy do módulo.
        if company_id == scope.primary_tenant_id:
            if manage:
                return scope.can_manage_company(company_id)
            return True

        if not scope.can_view_company(company_id):
            return False

        if resource is not None or action is not None:
            if resource is None or action is None:
                return False
            return scope.has_related_capability(company_id, resource, action)

        if manage:
            return scope.can_manage_company(company_id)
        return True

    @classmethod
    def require_company_access(cls, request, company, **options):
        cls.require_tenant(request)
        if not cls.can_access_company(request, company, **options):
            raise PermissionDenied(cls.ACCESS_DENIED_MESSAGE)
        return company

    @staticmethod
    def company_from_object(obj, company_path):
        """Resolve caminhos como ``empresa`` ou ``base__empresa``."""
        value = obj
        for attribute in str(company_path).replace('.', '__').split('__'):
            if not attribute:
                return None
            try:
                value = getattr(value, attribute)
            except (AttributeError, ObjectDoesNotExist):
                return None
            if value is None:
                return None
        return value

    @classmethod
    def can_access_object(cls, request, obj, *, company_path, **options):
        company = cls.company_from_object(obj, company_path)
        return cls.can_access_company(request, company, **options)

    @classmethod
    def require_object_access(cls, request, obj, *, company_path, **options):
        cls.require_tenant(request)
        if not cls.can_access_object(
            request,
            obj,
            company_path=company_path,
            **options,
        ):
            raise PermissionDenied(cls.ACCESS_DENIED_MESSAGE)
        return obj
