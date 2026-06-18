from estoque.models import Perfil


def secure_queryset_insumos(queryset, user, campo_base='base'):

    perfil = user.perfil
    if perfil.is_admin:
        return queryset

    filtro = {
        f'{campo_base}__in': perfil.regionais.all()
    }

    return queryset.filter(**filtro)