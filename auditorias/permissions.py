from django.core.exceptions import ObjectDoesNotExist, PermissionDenied


def perfil_do_usuario(usuario):
    try:
        return usuario.perfil
    except (AttributeError, ObjectDoesNotExist):
        return None

def usuario_e_admin(usuario):
    if not usuario or not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    perfil = perfil_do_usuario(usuario)
    return bool(perfil and perfil.is_admin)

def usuario_tem_acesso_base(usuario, base):
    if usuario_e_admin(usuario):
        return True
    perfil = perfil_do_usuario(usuario)
    return bool(
        perfil
        and perfil.empresa_id == base.empresa_id
        and perfil.regionais.filter(pk=base.pk).exists()
    )

def exigir_acesso_base(usuario, base):
    if not usuario_tem_acesso_base(usuario, base):
        raise PermissionDenied('Usuário sem acesso a esta base.')

def exigir_admin(usuario):
    if not usuario_e_admin(usuario):
        raise PermissionDenied('Apenas administradores podem executar esta ação.')
