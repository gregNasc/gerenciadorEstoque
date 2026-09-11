from .models import AuditoriaBase, AuditoriaDivergencia, CampanhaAuditoria
from .permissions import (
    ACAO_VISUALIZAR,
    RECURSO_AUDITORIAS,
    perfil_do_usuario,
)
from estoque.security import secure_company_queryset


def campanhas_visiveis(user, *, action=ACAO_VISUALIZAR):
    qs = CampanhaAuditoria.objects.select_related('empresa', 'criado_por')
    empresas = secure_company_queryset(
        CampanhaAuditoria._meta.get_field('empresa').related_model.objects.all(),
        user,
        resource=RECURSO_AUDITORIAS,
        action=action,
    )
    qs = qs.filter(empresa__in=empresas)
    if getattr(user, 'is_superuser', False):
        return qs
    perfil = perfil_do_usuario(user)
    if not perfil:
        return qs.none()
    if perfil.is_admin:
        return qs
    return qs.filter(auditorias_bases__base__in=perfil.regionais.all()).distinct()

def auditorias_visiveis(user, *, action=ACAO_VISUALIZAR):
    qs = AuditoriaBase.objects.select_related('campanha__empresa', 'base')
    qs = qs.filter(campanha__in=campanhas_visiveis(user, action=action))
    if getattr(user, 'is_superuser', False):
        return qs
    perfil = perfil_do_usuario(user)
    if not perfil:
        return qs.none()
    if perfil.is_admin:
        return qs
    return qs.filter(base__in=perfil.regionais.all())

def divergencias_visiveis(user, *, action=ACAO_VISUALIZAR):
    return AuditoriaDivergencia.objects.filter(
        auditoria_base__in=auditorias_visiveis(user, action=action)
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
