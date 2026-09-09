from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

    from estoque.models import Empresa, Perfil


@dataclass(frozen=True, slots=True)
class TenantRequestContext:
    """Snapshot tenant-aware da requisicao, sem tomar decisoes de autorizacao."""

    primary_tenant: 'Empresa | None' = None
    related_tenant_ids: frozenset[int] = field(default_factory=frozenset)
    user_id: int | None = None
    profile_id: int | None = None
    profile_role: str | None = None
    is_platform_superuser: bool = False

    @classmethod
    def empty(cls, *, user_id=None, is_platform_superuser=False):
        return cls(
            user_id=user_id,
            is_platform_superuser=is_platform_superuser,
        )

    @classmethod
    def from_profile(
        cls,
        user: 'AbstractBaseUser',
        profile: 'Perfil',
        *,
        related_tenant_ids: Iterable[int] | None = None,
    ):
        primary_id = profile.empresa_id
        if related_tenant_ids is None:
            related_tenant_ids = (
                company.pk for company in profile.empresas_acesso_adicional.all()
            )
        related_ids = frozenset(
            int(company_id)
            for company_id in related_tenant_ids
            if company_id is not None and int(company_id) != primary_id
        )
        return cls(
            primary_tenant=profile.empresa,
            related_tenant_ids=related_ids,
            user_id=user.pk,
            profile_id=profile.pk,
            profile_role=profile.role,
            is_platform_superuser=bool(user.is_superuser),
        )

    @property
    def primary_tenant_id(self):
        return self.primary_tenant.pk if self.primary_tenant is not None else None

    @property
    def tenant_ids(self):
        """IDs representados no contexto; nao equivale a permissao de escrita."""
        if self.primary_tenant_id is None:
            return self.related_tenant_ids
        return frozenset((self.primary_tenant_id, *self.related_tenant_ids))

    @property
    def has_fixed_tenant(self):
        return self.primary_tenant is not None

    @property
    def is_empty(self):
        return not self.tenant_ids
