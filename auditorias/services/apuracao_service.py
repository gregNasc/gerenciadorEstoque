from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from estoque.models import Equipamento, Historico
from estoque.services.comunicado_service import ComunicadoService

from auditorias.models import (
    AuditoriaBase,
    AuditoriaDivergencia,
    AuditoriaEvento,
    AuditoriaResolucao,
)
from auditorias.permissions import exigir_acesso_base, exigir_admin, usuario_e_admin


class ApuracaoService:
    @staticmethod
    @transaction.atomic
    def solicitar_correcao(auditoria_base, usuario, *, prazo_correcao_em, orientacoes):
        exigir_admin(usuario)
        auditoria = AuditoriaBase.objects.select_for_update().select_related(
            'base', 'campanha__empresa'
        ).get(pk=auditoria_base.pk)
        agora = timezone.now()
        if auditoria.finalizada_em:
            raise ValidationError('O resultado já foi validado e não pode receber nova solicitação de correção.')
        if auditoria.status not in (
            AuditoriaBase.Status.ENVIADA,
            AuditoriaBase.Status.COM_DIVERGENCIAS,
            AuditoriaBase.Status.EM_REGULARIZACAO,
        ):
            raise ValidationError('A auditoria precisa estar enviada para solicitar correções.')
        if prazo_correcao_em <= agora:
            raise ValidationError('O prazo de correção deve estar no futuro.')
        if not orientacoes.strip():
            raise ValidationError('Informe as orientações para a base.')

        auditoria.status = AuditoriaBase.Status.EM_REGULARIZACAO
        auditoria.correcao_solicitada_em = agora
        auditoria.correcao_solicitada_por = usuario
        auditoria.prazo_correcao_em = prazo_correcao_em
        auditoria.orientacoes_correcao = orientacoes.strip()
        auditoria.save(update_fields=[
            'status', 'correcao_solicitada_em', 'correcao_solicitada_por',
            'prazo_correcao_em', 'orientacoes_correcao',
        ])
        AuditoriaEvento.objects.create(
            auditoria_base=auditoria,
            tipo='CORRECAO_SOLICITADA',
            usuario=usuario,
            dados={
                'prazo_correcao_em': prazo_correcao_em.isoformat(),
                'orientacoes': orientacoes.strip(),
            },
        )
        transaction.on_commit(
            lambda: ComunicadoService.auditoria_correcao_solicitada(auditoria, usuario)
        )
        return auditoria

    @staticmethod
    @transaction.atomic
    def responder_divergencia(divergencia, usuario, justificativa):
        if usuario_e_admin(usuario):
            raise ValidationError('A resposta deve ser registrada por um usuário da base.')
        divergencia = AuditoriaDivergencia.objects.select_for_update().select_related(
            'auditoria_base__base'
        ).get(pk=divergencia.pk)
        auditoria = AuditoriaBase.objects.select_for_update().get(pk=divergencia.auditoria_base_id)
        exigir_acesso_base(usuario, auditoria.base)
        agora = timezone.now()
        if auditoria.status != AuditoriaBase.Status.EM_REGULARIZACAO:
            raise ValidationError('A auditoria não está em período de correção.')
        if not auditoria.prazo_correcao_em or agora > auditoria.prazo_correcao_em:
            raise ValidationError('O prazo para correções foi encerrado.')
        if not justificativa.strip():
            raise ValidationError('Informe a justificativa ou providência adotada.')
        if divergencia.status in (
            AuditoriaDivergencia.Status.RESOLVIDA,
            AuditoriaDivergencia.Status.CANCELADA,
        ):
            raise ValidationError('Esta divergência já foi encerrada.')

        divergencia.justificativa_base = justificativa.strip()
        divergencia.respondida_em = agora
        divergencia.respondida_por = usuario
        divergencia.status = AuditoriaDivergencia.Status.EM_ANALISE
        divergencia.save(update_fields=[
            'justificativa_base', 'respondida_em', 'respondida_por', 'status',
        ])
        AuditoriaEvento.objects.create(
            auditoria_base=auditoria,
            divergencia=divergencia,
            tipo='DIVERGENCIA_RESPONDIDA_PELA_BASE',
            usuario=usuario,
            dados={'justificativa': justificativa.strip()},
        )
        return divergencia

    @staticmethod
    @transaction.atomic
    def validar_resultado(auditoria_base, usuario):
        exigir_admin(usuario)
        auditoria = AuditoriaBase.objects.select_for_update().select_related(
            'base', 'campanha__empresa'
        ).get(pk=auditoria_base.pk)
        if auditoria.finalizada_em:
            raise ValidationError('O resultado desta auditoria já foi validado.')
        if auditoria.status not in (
            AuditoriaBase.Status.ENVIADA,
            AuditoriaBase.Status.COM_DIVERGENCIAS,
            AuditoriaBase.Status.EM_REGULARIZACAO,
        ):
            raise ValidationError('A auditoria precisa estar enviada para validação.')

        agora = timezone.now()
        divergencias_ausentes = list(
            auditoria.divergencias.select_for_update(of=('self',)).select_related('equipamento').filter(
                tipo=AuditoriaDivergencia.Tipo.NAO_LOCALIZADO,
            ).exclude(
                status__in=[
                    AuditoriaDivergencia.Status.RESOLVIDA,
                    AuditoriaDivergencia.Status.CANCELADA,
                ]
            )
        )
        inativados = 0
        for divergencia in divergencias_ausentes:
            if not divergencia.equipamento_id:
                continue
            equipamento = Equipamento.objects.select_for_update().get(pk=divergencia.equipamento_id)
            status_anterior = equipamento.status
            if equipamento.status != 'INATIVO':
                equipamento.status = 'INATIVO'
                equipamento.save(update_fields=['status'])
                inativados += 1
                Historico.objects.create(
                    equipamento=equipamento,
                    tipo_acao='AUDITORIA_REGULARIZADA',
                    usuario=usuario,
                    detalhes={
                        'acao': 'INATIVADO_NA_VALIDACAO',
                        'auditoria_base_id': auditoria.pk,
                        'divergencia_id': divergencia.pk,
                        'status_anterior': status_anterior,
                        'status_novo': 'INATIVO',
                        'base_mantida_id': equipamento.regional_id,
                    },
                )
            AuditoriaResolucao.objects.get_or_create(
                divergencia=divergencia,
                defaults={
                    'tipo': AuditoriaResolucao.Tipo.AJUSTE_ADMINISTRATIVO,
                    'justificativa': 'Equipamento não localizado; inativado na validação do resultado.',
                    'base_anterior': equipamento.regional,
                    'nova_base': equipamento.regional,
                    'resolvida_por': usuario,
                    'dados': {'status_anterior': status_anterior, 'status_novo': 'INATIVO'},
                },
            )
            divergencia.status = AuditoriaDivergencia.Status.RESOLVIDA
            divergencia.resolvida_em = agora
            divergencia.save(update_fields=['status', 'resolvida_em'])

        auditoria.status = AuditoriaBase.Status.FINALIZADA
        auditoria.finalizada_em = agora
        auditoria.finalizada_por = usuario
        auditoria.save(update_fields=['status', 'finalizada_em', 'finalizada_por'])
        AuditoriaEvento.objects.create(
            auditoria_base=auditoria,
            tipo='RESULTADO_VALIDADO',
            usuario=usuario,
            dados={
                'fonte_de_verdade': True,
                'equipamentos_nao_localizados': len(divergencias_ausentes),
                'equipamentos_inativados': inativados,
            },
        )
        transaction.on_commit(lambda: ComunicadoService.auditoria_finalizada(auditoria, usuario))
        return auditoria
