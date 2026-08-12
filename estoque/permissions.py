from estoque.policies.compras import GruposCorporativos


def _no_grupo(user, nome):
    return bool(user and user.is_authenticated and user.groups.filter(name=nome).exists())


def pode_gerenciar_sick(user):
    return (
        user.perfil.is_admin or
        _no_grupo(user, GruposCorporativos.SICK_GERENCIAR)
    )

def pode_enviar_comunicados(user):
    return (
        user.perfil.is_admin or
        _no_grupo(user, GruposCorporativos.COMUNICADOS_EDITOR)
    )

def pode_realizar_manutencao_sick(user):
    return _no_grupo(user, GruposCorporativos.SICK_MANUTENCAO)
