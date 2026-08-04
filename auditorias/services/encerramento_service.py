from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from auditorias.models import (
    AuditoriaBase,
    AuditoriaDivergencia,
    AuditoriaEvento,
    AuditoriaLeitura,
)
from auditorias.permissions import exigir_acesso_base


class EncerramentoService:
    @staticmethod
    @transaction.atomic
    def enviar(auditoria_base, usuario):
        auditoria = AuditoriaBase.objects.select_for_update().get(pk=auditoria_base.pk)
        exigir_acesso_base(usuario, auditoria.base)
        if auditoria.status not in (AuditoriaBase.Status.EM_ANDAMENTO, AuditoriaBase.Status.REABERTA):
            raise ValidationError('Somente auditorias em coleta podem ser enviadas.')

        equipamentos_lidos = set(
            AuditoriaLeitura.objects.filter(
                auditoria_base=auditoria,
                cancelada=False,
                equipamento__isnull=False,
            ).exclude(classificacao=AuditoriaLeitura.Classificacao.LEITURA_DUPLICADA)
            .values_list('equipamento_id', flat=True)
        )
        ausentes = auditoria.snapshot_equipamentos.exclude(equipamento_id__in=equipamentos_lidos)
        for snapshot in ausentes.iterator():
            divergencia, criada = AuditoriaDivergencia.objects.get_or_create(
                auditoria_base=auditoria,
                snapshot=snapshot,
                tipo=AuditoriaDivergencia.Tipo.NAO_LOCALIZADO,
                defaults={
                    'equipamento': snapshot.equipamento,
                    'base_esperada': snapshot.base_esperada,
                    'descricao': 'Equipamento esperado no snapshot não foi localizado.',
                },
            )
            if not criada and divergencia.status in (
                AuditoriaDivergencia.Status.CANCELADA,
                AuditoriaDivergencia.Status.RESOLVIDA,
            ):
                divergencia.status = AuditoriaDivergencia.Status.ABERTA
                divergencia.resolvida_em = None
                divergencia.save(update_fields=['status', 'resolvida_em'])

        agora = timezone.now()
        auditoria.enviada_em = agora
        auditoria.enviada_por = usuario
        auditoria.status = AuditoriaBase.Status.ENVIADA
        auditoria.save(update_fields=['enviada_em', 'enviada_por', 'status'])
        AuditoriaEvento.objects.create(
            auditoria_base=auditoria,
            tipo='AUDITORIA_ENVIADA',
            usuario=usuario,
            dados={
                'divergencias': auditoria.divergencias.count(),
                'status': auditoria.status,
            },
        )
        from estoque.services.comunicado_service import ComunicadoService
        transaction.on_commit(lambda: ComunicadoService.auditoria_enviada(auditoria, usuario))
        return auditoria

    @staticmethod
    def finalizar(auditoria_base, usuario):
        from auditorias.services.apuracao_service import ApuracaoService
        return ApuracaoService.validar_resultado(auditoria_base, usuario)

    @staticmethod
    def indicadores(auditoria_base):
        esperados = auditoria_base.snapshot_equipamentos.count()
        equipamentos_lidos = auditoria_base.leituras.filter(
            cancelada=False,
            equipamento__snapshots_auditoria__auditoria_base=auditoria_base,
        ).values('equipamento_id').distinct().count()
        corretos = auditoria_base.leituras.filter(
            classificacao=AuditoriaLeitura.Classificacao.CORRETO,
            cancelada=False,
        ).count()
        indevidos = auditoria_base.leituras.filter(
            equipamento__isnull=True,
            cancelada=False,
        ).count()
        conformidade = None
        if esperados:
            conformidade = round(corretos / esperados * 100, 2)
        elif not indevidos:
            conformidade = 100.0
        return {
            'esperados': esperados,
            'lidos': equipamentos_lidos,
            'leituras_total': auditoria_base.leituras.filter(cancelada=False).count(),
            'corretos': corretos,
            'divergencias_abertas': auditoria_base.divergencias.exclude(
                status__in=[AuditoriaDivergencia.Status.RESOLVIDA, AuditoriaDivergencia.Status.CANCELADA]
            ).count(),
            'conformidade': conformidade,
        }
