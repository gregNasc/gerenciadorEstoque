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
    perfil = getattr(user, 'perfil', None)

    # Usuário sem perfil → sem acesso
    if not perfil:
        return qs.none()

    # Admin → acesso total
    if perfil.is_admin:
        return qs

    # Sem empresa → bloqueia
    if not perfil.empresa:
        return qs.none()

    # Filtra pela empresa
    qs = qs.filter(**{campo_empresa: perfil.empresa})

    # Gestor / Operador → precisam ter regionais vinculadas
    if perfil.is_gestor or perfil.is_operador:
        regionais = perfil.regionais.all()

        if not regionais.exists():
            return qs.none()

        return qs.filter(**{f"{campo_regional}__in": regionais})

    # Qualquer outro caso → bloqueia
    return qs.none()