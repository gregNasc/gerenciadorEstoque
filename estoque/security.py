from django.core.exceptions import PermissionDenied

from estoque.models import CapacidadeRelacionamentoEmpresa, Equipamento
from estoque.tenant_scope import TenantScope


def validar_empresa_objeto(obj, empresa):
    if hasattr(obj, 'regional'):
        if obj.regional.empresa != empresa:
            raise PermissionDenied
    elif hasattr(obj, 'equipamento'):
        if obj.equipamento.regional.empresa != empresa:
            raise PermissionDenied
    return obj


def _allowed_company_ids(scope, *, resource=None, action=None):
    if scope.is_platform_scope:
        return None
    if not scope.has_fixed_tenant:
        return frozenset()

    company_ids = {scope.primary_tenant_id}
    if resource is None and action is None:
        company_ids.update(scope.related_company_ids)
    elif resource is not None and action is not None:
        company_ids.update(
            company_id
            for company_id in scope.related_company_ids
            if scope.has_related_capability(company_id, resource, action)
        )
    return frozenset(company_ids)


def secure_queryset(
    qs,
    user,
    campo_empresa='regional__empresa',
    campo_regional='regional',
    *,
    resource=None,
    action=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
):
    """Aplica tenant, capability e Bases a um QuerySet operacional.

    Para Equipamento, a capability padrão é EQUIPAMENTOS:VISUALIZAR. A
    permissão funcional da view continua sendo verificada separadamente.
    """
    perfil = getattr(user, 'perfil', None)
    if not perfil and not getattr(user, 'is_superuser', False):
        return qs.none()

    if qs.model is Equipamento:
        from auditorias.services.visibilidade_estoque_service import (
            VisibilidadeEstoqueAuditoriaService,
        )
        qs = VisibilidadeEstoqueAuditoriaService.ocultar_equipamentos(
            qs,
            campo_base=f'{campo_regional}_id',
        )
        resource = resource or CapacidadeRelacionamentoEmpresa.Recurso.EQUIPAMENTOS

    scope = TenantScope.for_user(user)
    if scope.is_platform_scope:
        return qs

    company_ids = _allowed_company_ids(
        scope,
        resource=resource,
        action=action if resource is not None else None,
    )
    if not company_ids:
        return qs.none()
    qs = qs.filter(**{f'{campo_empresa}__id__in': company_ids})

    if perfil.is_admin:
        return qs

    if perfil.role in {perfil.Role.GESTOR, perfil.Role.OPERADOR}:
        regional_ids = perfil.regionais.values_list('id', flat=True)
        return qs.filter(**{f'{campo_regional}__id__in': regional_ids})
    return qs.none()


def secure_base_queryset(
    qs,
    user,
    *,
    resource=CapacidadeRelacionamentoEmpresa.Recurso.EQUIPAMENTOS,
    action=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
):
    perfil = getattr(user, 'perfil', None)
    if not perfil and not getattr(user, 'is_superuser', False):
        return qs.none()

    scope = TenantScope.for_user(user)
    if scope.is_platform_scope:
        return qs

    company_ids = _allowed_company_ids(scope, resource=resource, action=action)
    if not company_ids:
        return qs.none()
    qs = qs.filter(empresa_id__in=company_ids)

    if perfil.is_admin:
        return qs
    if perfil.role in {perfil.Role.GESTOR, perfil.Role.OPERADOR}:
        return qs.filter(pk__in=perfil.regionais.values_list('pk', flat=True))
    return qs.none()


def secure_company_queryset(
    qs,
    user,
    *,
    resource=CapacidadeRelacionamentoEmpresa.Recurso.EQUIPAMENTOS,
    action=CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR,
):
    scope = TenantScope.for_user(user)
    if scope.is_platform_scope:
        return qs
    company_ids = _allowed_company_ids(scope, resource=resource, action=action)
    if not company_ids:
        return qs.none()
    return qs.filter(pk__in=company_ids)


def secure_history_queryset(qs, user):
    return secure_queryset(
        qs,
        user,
        campo_empresa='equipamento__regional__empresa',
        campo_regional='equipamento__regional',
        resource=CapacidadeRelacionamentoEmpresa.Recurso.EQUIPAMENTOS,
    )
