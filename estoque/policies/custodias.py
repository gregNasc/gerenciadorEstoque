from estoque.models import Custodia
from estoque.tenant_scope import TenantScope


class CustodiaAccessPolicy:
    VIEW = 'visualizar'
    MANAGE = 'gerenciar'

    @classmethod
    def custodias(cls, user, *, action=VIEW, queryset=None):
        queryset = queryset if queryset is not None else Custodia.objects.all()
        if not user or not user.is_authenticated:
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
