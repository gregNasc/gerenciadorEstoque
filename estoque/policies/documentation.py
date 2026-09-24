from django.db.models import Q

from estoque.models import CapacidadeRelacionamentoEmpresa, Empresa
from estoque.security import secure_company_queryset


class DocumentationAccessPolicy:
    RESOURCE = CapacidadeRelacionamentoEmpresa.Recurso.DOCUMENTACAO
    VIEW = CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR
    CREATE = CapacidadeRelacionamentoEmpresa.Acao.CRIAR
    EDIT = CapacidadeRelacionamentoEmpresa.Acao.EDITAR
    ADMIN = CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR

    @classmethod
    def companies(cls, user, *, action=VIEW):
        return secure_company_queryset(
            Empresa.objects.all(), user, resource=cls.RESOURCE, action=action
        )

    @classmethod
    def queryset(
        cls, queryset, user, *, action=VIEW, include_global=True, section=None
    ):
        if not user or not user.is_authenticated:
            return queryset.none()
        if user.is_superuser:
            return queryset
        empresas = cls.companies(user, action=action)
        filtro = Q(empresa__in=empresas)
        if include_global and action == cls.VIEW and section:
            from estoque.services.documentation_section_service import (
                DocumentationSectionService,
            )
            allow_global = DocumentationSectionService.allows_legacy_global(
                user, section
            )
        else:
            allow_global = False
        if allow_global:
            filtro |= Q(empresa__isnull=True)
        return queryset.filter(filtro).distinct()

    @classmethod
    def can_manage(cls, user):
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        perfil = getattr(user, 'perfil', None)
        return bool(
            perfil
            and perfil.empresa_id
            and (
                perfil.is_admin
                or user.has_perm('estoque.gerenciar_documentacao')
                or user.has_perm('insumos.gerenciar_documentacao')
            )
        )

    @staticmethod
    def owner_for_create(user):
        if getattr(user, 'is_superuser', False):
            return getattr(getattr(user, 'perfil', None), 'empresa', None)
        return getattr(getattr(user, 'perfil', None), 'empresa', None)
