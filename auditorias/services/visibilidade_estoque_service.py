from django.db.models import QuerySet
from django.utils import timezone

from auditorias.models import AuditoriaBase, CampanhaAuditoria


class VisibilidadeEstoqueAuditoriaService:
    MENSAGEM = 'Você está em período de auditoria.'

    STATUS_AUDITORIA_BLOQUEANTES = {
        AuditoriaBase.Status.NAO_INICIADA,
        AuditoriaBase.Status.DISPONIVEL,
        AuditoriaBase.Status.EM_ANDAMENTO,
        AuditoriaBase.Status.ENVIADA,
        AuditoriaBase.Status.COM_DIVERGENCIAS,
        AuditoriaBase.Status.EM_REGULARIZACAO,
        AuditoriaBase.Status.REABERTA,
    }
    STATUS_CAMPANHA_BLOQUEANTES = {
        CampanhaAuditoria.Status.AGENDADA,
        CampanhaAuditoria.Status.EM_ANDAMENTO,
    }

    @classmethod
    def auditorias_ativas(cls, *, agora=None) -> QuerySet:
        agora = agora or timezone.now()
        return AuditoriaBase.objects.filter(
            campanha__status__in=cls.STATUS_CAMPANHA_BLOQUEANTES,
            status__in=cls.STATUS_AUDITORIA_BLOQUEANTES,
            inicio_em__lte=agora,
            fim_em__gte=agora,
        )

    @classmethod
    def bases_bloqueadas(cls, *, agora=None) -> QuerySet:
        return cls.auditorias_ativas(agora=agora).values_list('base_id', flat=True)

    @classmethod
    def base_bloqueada(cls, base_id, *, agora=None) -> bool:
        if not base_id:
            return False
        return cls.auditorias_ativas(agora=agora).filter(base_id=base_id).exists()

    @classmethod
    def ocultar_equipamentos(cls, queryset, *, campo_base='regional_id'):
        return queryset.exclude(**{f'{campo_base}__in': cls.bases_bloqueadas()})
