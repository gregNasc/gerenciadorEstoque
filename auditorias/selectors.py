from django.db.models import Q

from .models import AuditoriaBase, AuditoriaDivergencia, CampanhaAuditoria
from .permissions import perfil_do_usuario, usuario_e_admin


def _escopo_usuario(user):
    if usuario_e_admin(user):
        return None
    perfil = perfil_do_usuario(user)
    if not perfil:
        return Q(pk__in=[])
    return Q(empresa_id=perfil.empresa_id, auditorias_bases__base__in=perfil.regionais.all())


def campanhas_visiveis(user):
    qs = CampanhaAuditoria.objects.select_related('empresa', 'criado_por')
    escopo = _escopo_usuario(user)
    return qs if escopo is None else qs.filter(escopo).distinct()


def auditorias_visiveis(user):
    qs = AuditoriaBase.objects.select_related('campanha__empresa', 'base')
    if usuario_e_admin(user):
        return qs
    perfil = perfil_do_usuario(user)
    if not perfil:
        return qs.none()
    return qs.filter(campanha__empresa_id=perfil.empresa_id, base__in=perfil.regionais.all())


def divergencias_visiveis(user):
    return AuditoriaDivergencia.objects.filter(
        auditoria_base__in=auditorias_visiveis(user)
    ).select_related(
        'auditoria_base__base', 'equipamento', 'leitura',
        'base_esperada', 'base_encontrada',
    )


def equipamentos_esperados(auditoria_base):
    return auditoria_base.snapshot_equipamentos.select_related('equipamento', 'base_esperada')


def equipamentos_com_transferencia_aberta():
    from estoque.models import Equipamento
    return Equipamento.objects.filter(
        transferenciaitem__transferencia__status__in=['PENDENTE', 'EM_TRANSITO']
    ).distinct()


def emprestimos_vigentes():
    from estoque.models import Emprestimo
    return Emprestimo.objects.exclude(status__in=['FINALIZADO', 'CANCELADO'])
