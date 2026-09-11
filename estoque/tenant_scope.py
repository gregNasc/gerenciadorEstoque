from dataclasses import dataclass, field

from django.db import DatabaseError

from estoque.models import (
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    Perfil,
)
from estoque.tenant_context import TenantRequestContext


@dataclass(frozen=True, slots=True)
class TenantScope:
    """Escopo central de empresas, resolvido sem autorizar objetos de dominio."""

    user_id: int | None = None
    primary_company: Empresa | None = None
    visible_company_ids: frozenset[int] = field(default_factory=frozenset)
    manageable_company_ids: frozenset[int] = field(default_factory=frozenset)
    related_company_ids: frozenset[int] = field(default_factory=frozenset)
    related_capabilities: frozenset[tuple[int, str, str]] = field(
        default_factory=frozenset
    )
    profile_id: int | None = None
    profile_role: str | None = None
    is_platform_scope: bool = False

    @classmethod
    def empty(cls, *, user_id=None):
        return cls(user_id=user_id)

    @classmethod
    def for_user(cls, user, *, context=None):
        if not user or not user.is_authenticated:
            return cls.empty()

        context_provided = context is not None
        if context is None:
            cached = getattr(user, '_tenant_scope_request_cache', None)
            if isinstance(cached, cls) and cached.user_id == user.pk:
                return cached
            context = cls._load_context(user)
        elif context.user_id != user.pk:
            # Um contexto de outra identidade nunca pode ampliar este usuario.
            context = TenantRequestContext.empty(
                user_id=user.pk,
                is_platform_superuser=bool(user.is_superuser),
            )

        if user.is_superuser:
            scope = cls(
                user_id=user.pk,
                primary_company=context.primary_tenant,
                visible_company_ids=context.tenant_ids,
                manageable_company_ids=context.tenant_ids,
                related_company_ids=context.related_tenant_ids,
                profile_id=context.profile_id,
                profile_role=context.profile_role,
                is_platform_scope=True,
            )
            if context_provided:
                user._tenant_scope_request_cache = scope
            return scope

        primary_id = context.primary_tenant_id
        visible_ids = (
            frozenset((primary_id,)) if primary_id is not None else frozenset()
        )
        related_ids = frozenset()
        related_capabilities = frozenset()
        manageable_ids = frozenset()
        if context.profile_role == Perfil.Role.ADMIN and primary_id:
            related_capabilities = cls._load_relationship_capabilities(primary_id)
            allowed_related_ids = frozenset(
                company_id for company_id, _resource, _action in related_capabilities
            )
            related_ids = context.related_tenant_ids & allowed_related_ids
            related_capabilities = frozenset(
                capability
                for capability in related_capabilities
                if capability[0] in related_ids
            )
            visible_ids = visible_ids | related_ids
            manageable_related_ids = frozenset(
                company_id
                for company_id, resource, action in related_capabilities
                if resource == CapacidadeRelacionamentoEmpresa.Recurso.OPERACAO
                and action == CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR
            )
            manageable_ids = frozenset((primary_id,)) | manageable_related_ids

        scope = cls(
            user_id=user.pk,
            primary_company=context.primary_tenant,
            visible_company_ids=visible_ids,
            manageable_company_ids=manageable_ids,
            related_company_ids=related_ids,
            related_capabilities=related_capabilities,
            profile_id=context.profile_id,
            profile_role=context.profile_role,
            is_platform_scope=False,
        )
        if context_provided:
            user._tenant_scope_request_cache = scope
        return scope

    @staticmethod
    def _load_context(user):
        try:
            profile = (
                Perfil.objects.select_related('empresa')
                .prefetch_related('empresas_acesso_adicional')
                .filter(user=user)
                .first()
            )
        except DatabaseError:
            profile = None

        if profile is None:
            return TenantRequestContext.empty(
                user_id=user.pk,
                is_platform_superuser=bool(user.is_superuser),
            )
        return TenantRequestContext.from_profile(user, profile)

    @staticmethod
    def _load_relationship_capabilities(primary_company_id):
        try:
            rows = CapacidadeRelacionamentoEmpresa.objects.filter(
                relacionamento__empresa_origem_id=primary_company_id,
                relacionamento__ativo=True,
                ativo=True,
            ).values_list(
                'relacionamento__empresa_destino_id',
                'recurso',
                'acao',
            )
            return frozenset(rows)
        except DatabaseError:
            # A empresa principal permanece, mas nenhuma relacao e presumida.
            return frozenset()

    def visible_companies(self):
        if self.is_platform_scope:
            # O uso global e explicito e exclusivo do Superuser da plataforma.
            return Empresa.objects.all()
        if not self.visible_company_ids:
            return Empresa.objects.none()
        return Empresa.objects.filter(pk__in=self.visible_company_ids)

    def can_view_company(self, company):
        company_id = self._company_id(company)
        if company_id is None:
            return False
        return self.is_platform_scope or company_id in self.visible_company_ids

    def can_manage_company(self, company):
        company_id = self._company_id(company)
        if company_id is None:
            return False
        return self.is_platform_scope or company_id in self.manageable_company_ids

    def has_related_capability(self, company, resource, action):
        company_id = self._company_id(company)
        if company_id is None:
            return False
        if self.is_platform_scope:
            return True
        return (company_id, str(resource), str(action)) in self.related_capabilities

    @staticmethod
    def _company_id(company):
        value = getattr(company, 'pk', company)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def primary_tenant(self):
        return self.primary_company

    @property
    def primary_tenant_id(self):
        return self.primary_company.pk if self.primary_company is not None else None

    @property
    def tenant_ids(self):
        return self.visible_company_ids

    @property
    def related_tenant_ids(self):
        return self.related_company_ids

    @property
    def is_platform_superuser(self):
        return self.is_platform_scope

    @property
    def has_fixed_tenant(self):
        return self.primary_company is not None

    @property
    def is_empty(self):
        return not self.is_platform_scope and not self.visible_company_ids
