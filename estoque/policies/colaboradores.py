from estoque.models import Colaborador
from estoque.tenant_scope import TenantScope


class ColaboradorAccessPolicy:
    VIEW = 'visualizar'
    MANAGE = 'gerenciar'

    @classmethod
    def colaboradores(cls, user, *, action=VIEW, queryset=None):
        queryset = queryset if queryset is not None else Colaborador.objects.all()
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
