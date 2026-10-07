from django.db.models import Q

from estoque.models import LocalFisico
from estoque.tenant_scope import TenantScope


class LocalFisicoAccessPolicy:
    VIEW = 'visualizar'
    MANAGE = 'gerenciar'

    @classmethod
    def locais(cls, user, *, action=VIEW, queryset=None):
        queryset = queryset if queryset is not None else LocalFisico.objects.all()
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
            Q(empresa_id__in=company_ids)
            | Q(vinculos_base__base__empresa_id__in=company_ids),
            ativo=True,
            empresa__ativa=True,
        ).distinct()
