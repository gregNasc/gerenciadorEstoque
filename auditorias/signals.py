from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from estoque.models import Historico, Transferencia

from .models import AuditoriaDivergencia, AuditoriaEvento, AuditoriaResolucao


@receiver(post_save, sender=Transferencia)
def concluir_divergencia_apos_recebimento(sender, instance, **kwargs):
    if instance.status != Transferencia.Status.CONCLUIDA:
        return
    resolucao_id = AuditoriaResolucao.objects.filter(
        transferencia=instance,
        tipo=AuditoriaResolucao.Tipo.TRANSFERIR,
    ).values_list('pk', flat=True).first()
    if not resolucao_id:
        return
    with transaction.atomic():
        resolucao = AuditoriaResolucao.objects.select_for_update(of=('self',)).select_related(
            'divergencia__auditoria_base', 'divergencia__equipamento'
        ).get(pk=resolucao_id)
        divergencia = AuditoriaDivergencia.objects.select_for_update().get(pk=resolucao.divergencia_id)
        if divergencia.status != AuditoriaDivergencia.Status.AGUARDANDO_TRANSFERENCIA:
            return
        divergencia.status = AuditoriaDivergencia.Status.RESOLVIDA
        divergencia.resolvida_em = timezone.now()
        divergencia.save(update_fields=['status', 'resolvida_em'])
        AuditoriaEvento.objects.create(
            auditoria_base=divergencia.auditoria_base,
            divergencia=divergencia,
            tipo='TRANSFERENCIA_RECEBIDA',
            usuario=instance.solicitado_por,
            dados={'transferencia_id': instance.pk},
        )
        if divergencia.equipamento_id and instance.solicitado_por_id:
            Historico.objects.create(
                equipamento=divergencia.equipamento,
                tipo_acao='AUDITORIA_REGULARIZADA',
                usuario=instance.solicitado_por,
                detalhes={
                    'auditoria_base_id': divergencia.auditoria_base_id,
                    'divergencia_id': divergencia.pk,
                    'transferencia_id': instance.pk,
                    'nova_base_id': instance.regional_destino_id,
                },
            )
        if instance.solicitado_por_id:
            from estoque.services.comunicado_service import ComunicadoService
            transaction.on_commit(
                lambda: ComunicadoService.criar_acao(
                    titulo=f'Transferência de auditoria {instance.protocolo} recebida',
                    mensagem=(
                        f'A base {instance.regional_destino.nome} confirmou o recebimento '
                        f'da transferência criada para regularização da auditoria.'
                    ),
                    usuario=instance.solicitado_por,
                    bases=[instance.regional_origem, instance.regional_destino],
                    empresa=instance.regional_destino.empresa,
                    dados={
                        'template_codigo': 'transferencia_recebida',
                        'divergencia_id': divergencia.pk,
                    },
                    url=f'/transferencias/{instance.pk}/',
                )
            )
