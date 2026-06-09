USUARIOS_MANUTENCAO = {
    'rafael.ribeiro',
}


def pode_gerenciar_sick(user):
    return (
        user.perfil.is_admin or
        user.username in USUARIOS_MANUTENCAO
    )


def pode_enviar_comunicados(user):
    return (
        user.perfil.is_admin or
        user.username in USUARIOS_MANUTENCAO
    )


def pode_realizar_manutencao_sick(user):
    return (
        user.perfil.is_admin or
        user.username == 'rafael.ribeiro'
    )