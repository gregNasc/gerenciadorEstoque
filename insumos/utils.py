from estoque.models import Perfil


def secure_queryset_insumos(queryset, user, campo_base='base'):
    perfil = getattr(user, 'perfil', None)
    if not perfil:
        return queryset.none()
    if perfil.is_admin:
        return queryset

    if not perfil.empresa_id:
        return queryset.none()

    bases_autorizadas = perfil.regionais.filter(empresa_id=perfil.empresa_id)

    filtro = {
        f'{campo_base}__in': bases_autorizadas
    }

    return queryset.filter(**filtro)
