from django.core.exceptions import PermissionDenied

from estoque.models import Custodia, Perfil
from estoque.tenant_scope import TenantScope


class CustodiaAccessPolicy:
    VIEW = 'visualizar'
    MANAGE = 'gerenciar'
    USUARIOS_SEM_GESTAO = frozenset({'jose.barboza'})

    @classmethod
    def permite(cls, user, action=VIEW):
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        role = Perfil.objects.filter(user_id=user.pk).values_list(
            'role', flat=True,
        ).first()
        if role != Perfil.Role.ADMIN:
            return False
        if action == cls.VIEW:
            return True
        if action == cls.MANAGE:
            return user.get_username().strip().lower() not in cls.USUARIOS_SEM_GESTAO
        return False

    @classmethod
    def exigir(cls, user, action=VIEW):
        if not cls.permite(user, action):
            raise PermissionDenied('Usuário sem permissão para esta operação de Custódia.')

    @classmethod
    def empresas(cls, user, *, action=VIEW, queryset=None):
        from estoque.models import Empresa

        queryset = queryset if queryset is not None else Empresa.objects.all()
        if not cls.permite(user, action):
            return queryset.none()
        scope = TenantScope.fresh_for_user(user)
        if scope.is_platform_scope:
            return queryset.filter(ativa=True)
        company_ids = (
            scope.visible_company_ids
            if action == cls.VIEW
            else scope.manageable_company_ids
        )
        if not company_ids:
            return queryset.none()
        return queryset.filter(pk__in=company_ids, ativa=True)

    @classmethod
    def custodias(cls, user, *, action=VIEW, queryset=None):
        queryset = queryset if queryset is not None else Custodia.objects.all()
        if not cls.permite(user, action):
            return queryset.none()

        scope = TenantScope.fresh_for_user(user)
        if scope.is_platform_scope:
            return queryset
        if action == cls.VIEW:
            company_ids = scope.visible_company_ids
        elif action == cls.MANAGE:
            company_ids = scope.manageable_company_ids
        else:
            return queryset.none()
        if not company_ids:
            return queryset.none()
        return queryset.filter(
            empresa_id__in=company_ids,
            empresa__ativa=True,
        )
