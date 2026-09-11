from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

from estoque.models import CapacidadeRelacionamentoEmpresa
from estoque.tenant_scope import TenantScope


RECURSO_AUDITORIAS = CapacidadeRelacionamentoEmpresa.Recurso.AUDITORIAS
ACAO_VISUALIZAR = CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR
ACAO_CRIAR = CapacidadeRelacionamentoEmpresa.Acao.CRIAR
ACAO_EDITAR = CapacidadeRelacionamentoEmpresa.Acao.EDITAR
ACAO_APROVAR = CapacidadeRelacionamentoEmpresa.Acao.APROVAR
ACAO_EXPORTAR = CapacidadeRelacionamentoEmpresa.Acao.EXPORTAR
ACAO_ADMINISTRAR = CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR


def perfil_do_usuario(usuario):
    try:
        return usuario.perfil
    except (AttributeError, ObjectDoesNotExist):
        return None

def usuario_e_admin(usuario, empresa=None, *, acao=ACAO_ADMINISTRAR):
    if not usuario or not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    perfil = perfil_do_usuario(usuario)
    if not perfil or not perfil.is_admin:
        return False
    if empresa is None:
        # Consulta somente funcional. Nunca deve ser usada para autorizar um
        # objeto; nesses casos a empresa é obrigatória.
        return True
    empresa_id = getattr(empresa, 'pk', empresa)
    if perfil.empresa_id == empresa_id:
        return True
    return TenantScope.for_user(usuario).has_related_capability(
        empresa_id,
        RECURSO_AUDITORIAS,
        acao,
    )

def usuario_tem_acesso_base(usuario, base, *, acao=ACAO_VISUALIZAR):
    if usuario_e_admin(usuario, base.empresa, acao=acao):
        return True
    perfil = perfil_do_usuario(usuario)
    return bool(
        perfil
        and perfil.empresa_id == base.empresa_id
        and perfil.regionais.filter(pk=base.pk).exists()
    )

def exigir_acesso_base(usuario, base, *, acao=ACAO_VISUALIZAR):
    if not usuario_tem_acesso_base(usuario, base, acao=acao):
        raise PermissionDenied('Usuário sem acesso a esta base.')

def exigir_admin(usuario, empresa, *, acao=ACAO_ADMINISTRAR):
    if not usuario_e_admin(usuario, empresa, acao=acao):
        raise PermissionDenied('Apenas administradores podem executar esta ação.')
