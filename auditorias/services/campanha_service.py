from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from auditorias.models import AuditoriaBase, AuditoriaEvento, CampanhaAuditoria
from auditorias.permissions import exigir_admin


class CampanhaService:
    @staticmethod
    @transaction.atomic
    def criar_campanha(*, empresa, nome, criado_por, descricao='', instrucoes=''):
        exigir_admin(criado_por)
        return CampanhaAuditoria.objects.create(
            empresa=empresa,
            nome=nome,
            descricao=descricao,
            instrucoes=instrucoes,
            criado_por=criado_por,
        )

    @staticmethod
    @transaction.atomic
    def adicionar_base(*, campanha, base, inicio_em, fim_em, usuario):
        exigir_admin(usuario)
        campanha = CampanhaAuditoria.objects.select_for_update().get(pk=campanha.pk)
        if campanha.status != CampanhaAuditoria.Status.RASCUNHO:
            raise ValidationError('Bases só podem ser adicionadas a campanhas em rascunho.')
        auditoria = AuditoriaBase(
            campanha=campanha,
            base=base,
            inicio_em=inicio_em,
            fim_em=fim_em,
        )
        auditoria.full_clean()
        auditoria.save()
        return auditoria

    @staticmethod
    @transaction.atomic
    def agendar(campanha, usuario):
        exigir_admin(usuario)
        campanha = CampanhaAuditoria.objects.select_for_update().get(pk=campanha.pk)
        if campanha.status != CampanhaAuditoria.Status.RASCUNHO:
            raise ValidationError('A campanha não está em rascunho.')
        if not campanha.auditorias_bases.exists():
            raise ValidationError('Inclua ao menos uma base antes de agendar.')
        campanha.status = CampanhaAuditoria.Status.AGENDADA
        campanha.save(update_fields=['status'])
        return campanha

    @staticmethod
    @transaction.atomic
    def atualizar_periodo_base(auditoria_base, *, inicio_em, fim_em, usuario, justificativa=''):
        exigir_admin(usuario)
        auditoria = AuditoriaBase.objects.select_for_update().get(pk=auditoria_base.pk)
        iniciado = bool(auditoria.snapshot_criado_em)
        if iniciado and not justificativa.strip():
            raise ValidationError('Alterações de data após o início exigem justificativa.')
        anteriores = {'inicio_em': auditoria.inicio_em.isoformat(), 'fim_em': auditoria.fim_em.isoformat()}
        auditoria.inicio_em = inicio_em
        auditoria.fim_em = fim_em
        auditoria.full_clean()
        auditoria.save(update_fields=['inicio_em', 'fim_em'])
        if iniciado:
            AuditoriaEvento.objects.create(
                auditoria_base=auditoria,
                tipo='PERIODO_ALTERADO',
                usuario=usuario,
                dados={**anteriores, 'novo_inicio_em': inicio_em.isoformat(), 'novo_fim_em': fim_em.isoformat(), 'justificativa': justificativa},
            )
        return auditoria

    @staticmethod
    @transaction.atomic
    def dispensar_base(auditoria_base, usuario, justificativa):
        exigir_admin(usuario)
        if not justificativa.strip():
            raise ValidationError('Informe a justificativa da dispensa.')
        auditoria = AuditoriaBase.objects.select_for_update().get(pk=auditoria_base.pk)
        if auditoria.status in (AuditoriaBase.Status.FINALIZADA, AuditoriaBase.Status.DISPENSADA):
            raise ValidationError('Esta base já foi encerrada.')
        auditoria.status = AuditoriaBase.Status.DISPENSADA
        auditoria.observacoes = '\n'.join(filter(None, [auditoria.observacoes, f'Dispensa: {justificativa}']))
        auditoria.save(update_fields=['status', 'observacoes'])
        AuditoriaEvento.objects.create(
            auditoria_base=auditoria,
            tipo='BASE_DISPENSADA',
            usuario=usuario,
            dados={'justificativa': justificativa},
        )
        return auditoria

    @staticmethod
    @transaction.atomic
    def encerrar_campanha(campanha, usuario):
        exigir_admin(usuario)
        campanha = CampanhaAuditoria.objects.select_for_update().get(pk=campanha.pk)
        pendentes = campanha.auditorias_bases.exclude(
            status__in=[
                AuditoriaBase.Status.FINALIZADA,
                AuditoriaBase.Status.EXPIRADA,
                AuditoriaBase.Status.DISPENSADA,
            ]
        )
        if pendentes.exists():
            raise ValidationError('Todas as bases devem estar finalizadas, expiradas ou dispensadas.')
        campanha.status = CampanhaAuditoria.Status.ENCERRADA
        campanha.encerrado_em = timezone.now()
        campanha.save(update_fields=['status', 'encerrado_em'])
        return campanha

    @staticmethod
    @transaction.atomic
    def cancelar_campanha(campanha, usuario, justificativa):
        exigir_admin(usuario)
        if not justificativa.strip():
            raise ValidationError('Informe a justificativa do cancelamento.')
        campanha = CampanhaAuditoria.objects.select_for_update().get(pk=campanha.pk)
        if campanha.status == CampanhaAuditoria.Status.ENCERRADA:
            raise ValidationError('Campanha encerrada não pode ser cancelada.')
        campanha.status = CampanhaAuditoria.Status.CANCELADA
        campanha.save(update_fields=['status'])
        for auditoria in campanha.auditorias_bases.all():
            AuditoriaEvento.objects.create(
                auditoria_base=auditoria,
                tipo='CAMPANHA_CANCELADA',
                usuario=usuario,
                dados={'justificativa': justificativa},
            )
        return campanha

    @staticmethod
    @transaction.atomic
    def reabrir_base(auditoria_base, usuario, justificativa):
        exigir_admin(usuario)
        if not justificativa.strip():
            raise ValidationError('Informe a justificativa da reabertura.')
        auditoria = AuditoriaBase.objects.select_for_update().get(pk=auditoria_base.pk)
        if not auditoria.snapshot_criado_em:
            raise ValidationError('Não é possível reabrir uma auditoria ainda não iniciada.')
        if auditoria.status not in (
            AuditoriaBase.Status.ENVIADA,
            AuditoriaBase.Status.COM_DIVERGENCIAS,
            AuditoriaBase.Status.EM_REGULARIZACAO,
        ):
            raise ValidationError('Esta auditoria não está em um estado que permita reabertura.')
        auditoria.status = AuditoriaBase.Status.REABERTA
        auditoria.versao_reabertura += 1
        auditoria.finalizada_em = None
        auditoria.finalizada_por = None
        auditoria.correcao_solicitada_em = None
        auditoria.correcao_solicitada_por = None
        auditoria.prazo_correcao_em = None
        auditoria.orientacoes_correcao = ''
        auditoria.save(update_fields=[
            'status', 'versao_reabertura', 'finalizada_em', 'finalizada_por',
            'correcao_solicitada_em', 'correcao_solicitada_por',
            'prazo_correcao_em', 'orientacoes_correcao',
        ])
        if auditoria.campanha.status != CampanhaAuditoria.Status.EM_ANDAMENTO:
            auditoria.campanha.status = CampanhaAuditoria.Status.EM_ANDAMENTO
            auditoria.campanha.save(update_fields=['status'])
        AuditoriaEvento.objects.create(
            auditoria_base=auditoria,
            tipo='AUDITORIA_REABERTA',
            usuario=usuario,
            dados={'justificativa': justificativa, 'versao': auditoria.versao_reabertura},
        )
        return auditoria

    @staticmethod
    @transaction.atomic
    def sincronizar_status_por_data(campanha=None):
        agora = timezone.now()
        qs = AuditoriaBase.objects.select_for_update().filter(
            status__in=[AuditoriaBase.Status.NAO_INICIADA, AuditoriaBase.Status.DISPONIVEL]
        )
        if campanha:
            qs = qs.filter(campanha=campanha)
        qs.filter(inicio_em__lte=agora, fim_em__gte=agora).update(status=AuditoriaBase.Status.DISPONIVEL)
        qs.filter(fim_em__lt=agora).update(status=AuditoriaBase.Status.EXPIRADA)
