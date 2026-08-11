from django.core.exceptions import PermissionDenied


def validar_empresa_objeto(obj, empresa):
    if hasattr(obj, "regional"):
        if obj.regional.empresa != empresa:
            raise PermissionDenied

    elif hasattr(obj, "equipamento"):
        if obj.equipamento.regional.empresa != empresa:
            raise PermissionDenied

    return obj

def secure_queryset(qs, user, campo_empresa='regional__empresa', campo_regional='regional'):
    from estoque.models import Equipamento

    perfil = getattr(user, 'perfil', None)
    if not perfil:
        return qs.none()

    # A auditoria usa snapshots próprios. Consultas comuns nunca devem revelar o
    # estoque vivo de uma base dentro da janela ativa, nem mesmo a administradores.
    if qs.model is Equipamento:
        from auditorias.services.visibilidade_estoque_service import (
            VisibilidadeEstoqueAuditoriaService,
        )
        qs = VisibilidadeEstoqueAuditoriaService.ocultar_equipamentos(
            qs,
            campo_base=f'{campo_regional}_id',
        )

    if perfil.is_admin:
        return qs

    if not perfil.empresa:
        return qs.none()

    # Filtro por empresa
    qs = qs.filter(**{campo_empresa: perfil.empresa})

    role = getattr(perfil, 'role', '')

    if role == 'gestor' or role == 'operador':
        regionais_ids = list(perfil.regionais.values_list('id', flat=True))
        if not regionais_ids:
            return qs.none()
        # Aplica filtro pelas regionais
        qs = qs.filter(**{f"{campo_regional}__id__in": regionais_ids})
        return qs

    return qs.none()
