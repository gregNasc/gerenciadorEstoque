from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from estoque.models import Equipamento

from auditorias.models import (
    AuditoriaBase,
    AuditoriaEvento,
    AuditoriaSnapshotEquipamento,
    CampanhaAuditoria,
)
from auditorias.permissions import exigir_acesso_base


class SnapshotService:
    @staticmethod
    @transaction.atomic
    def criar_snapshot(auditoria_base, usuario):
        auditoria = AuditoriaBase.objects.select_for_update().select_related(
            'base__empresa', 'campanha__empresa'
        ).get(pk=auditoria_base.pk)
        exigir_acesso_base(usuario, auditoria.base)
        agora = timezone.now()
        if auditoria.snapshot_criado_em or auditoria.snapshot_equipamentos.exists():
            raise ValidationError('O snapshot desta auditoria já foi criado.')
        if auditoria.campanha.status not in (
            CampanhaAuditoria.Status.AGENDADA,
            CampanhaAuditoria.Status.EM_ANDAMENTO,
        ):
            raise ValidationError('Agende a campanha antes de iniciar a coleta.')
        if auditoria.status not in (
            AuditoriaBase.Status.NAO_INICIADA,
            AuditoriaBase.Status.DISPONIVEL,
        ):
            raise ValidationError('Esta auditoria não pode ser iniciada.')
        if agora < auditoria.inicio_em or agora > auditoria.fim_em:
            raise ValidationError('A auditoria está fora da janela de coleta.')

        equipamentos = list(
            Equipamento.objects.filter(
                regional=auditoria.base,
                regional__empresa=auditoria.campanha.empresa,
            ).select_related('produto')
        )
        snapshots = [
            AuditoriaSnapshotEquipamento(
                auditoria_base=auditoria,
                equipamento=equipamento,
                base_esperada=auditoria.base,
                produto_id_snapshot=equipamento.produto_id,
                produto_descricao=(equipamento.produto.descricao if equipamento.produto else ''),
                categoria=(equipamento.produto.categoria if equipamento.produto else ''),
                codigo=equipamento.codigo,
                patrimonio=equipamento.patrimonio,
                numero_serie=equipamento.numero_serie,
                status=equipamento.status,
                tipo_uso=equipamento.finalidade,
                responsavel=equipamento.responsavel,
            )
            for equipamento in equipamentos
        ]
        AuditoriaSnapshotEquipamento.objects.bulk_create(snapshots)
        auditoria.snapshot_criado_em = agora
        auditoria.iniciada_em = agora
        auditoria.iniciada_por = usuario
        auditoria.status = AuditoriaBase.Status.EM_ANDAMENTO
        auditoria.save(update_fields=['snapshot_criado_em', 'iniciada_em', 'iniciada_por', 'status'])
        if auditoria.campanha.status == CampanhaAuditoria.Status.AGENDADA:
            auditoria.campanha.status = CampanhaAuditoria.Status.EM_ANDAMENTO
            auditoria.campanha.save(update_fields=['status'])
        AuditoriaEvento.objects.create(
            auditoria_base=auditoria,
            tipo='SNAPSHOT_CRIADO',
            usuario=usuario,
            dados={'quantidade': len(snapshots)},
        )
        from estoque.services.comunicado_service import ComunicadoService
        transaction.on_commit(lambda: ComunicadoService.auditoria_aberta(auditoria, usuario))
        return auditoria
