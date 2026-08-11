from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from estoque.models import Equipamento, Historico, Transferencia, TransferenciaItem
from estoque.services.comunicado_service import ComunicadoService


class TransferenciaService:
    @staticmethod
    @transaction.atomic
    def criar_por_divergencia(*, divergencia, base_destino, usuario, justificativa):
        from auditorias.models import AuditoriaBase, AuditoriaDivergencia, AuditoriaEvento, AuditoriaResolucao
        from auditorias.permissions import exigir_acesso_base

        if not justificativa.strip():
            raise ValidationError('Informe a justificativa da transferência.')
        divergencia = AuditoriaDivergencia.objects.select_for_update(of=('self',)).select_related(
            'auditoria_base__campanha', 'base_encontrada', 'base_esperada'
        ).get(pk=divergencia.pk)
        if divergencia.tipo != AuditoriaDivergencia.Tipo.OUTRA_BASE:
            raise ValidationError('Esta divergência não permite transferência direta.')
        if divergencia.status not in (
            AuditoriaDivergencia.Status.ABERTA,
            AuditoriaDivergencia.Status.EM_ANALISE,
        ):
            raise ValidationError('A divergência não está disponível para regularização.')
        if (
            divergencia.auditoria_base.status != AuditoriaBase.Status.EM_REGULARIZACAO
            or not divergencia.auditoria_base.prazo_correcao_em
            or timezone.now() > divergencia.auditoria_base.prazo_correcao_em
        ):
            raise ValidationError('A auditoria não está dentro do prazo de correção.')
        if not divergencia.equipamento_id or not divergencia.base_encontrada_id:
            raise ValidationError('A divergência não possui equipamento e base identificados.')
        exigir_acesso_base(usuario, divergencia.base_encontrada)
        if base_destino.empresa_id != divergencia.base_encontrada.empresa_id:
            raise ValidationError('A base de destino deve pertencer à mesma empresa.')
        if base_destino.pk == divergencia.base_encontrada_id:
            raise ValidationError('A base de destino deve ser diferente da origem física.')
        if hasattr(divergencia, 'resolucao'):
            raise ValidationError('Esta divergência já possui resolução.')

        equipamento = Equipamento.objects.select_for_update().get(pk=divergencia.equipamento_id)
        if TransferenciaItem.objects.filter(
            equipamento=equipamento,
            transferencia__status__in=[Transferencia.Status.PENDENTE, Transferencia.Status.EM_TRANSITO],
        ).exists():
            raise ValidationError('O equipamento possui uma transferência aberta.')

        transferencia = Transferencia.objects.create(
            protocolo=f'AUD-{uuid4().hex[:12].upper()}',
            solicitado_por=usuario,
            regional_origem=divergencia.base_encontrada,
            regional_destino=base_destino,
            status=Transferencia.Status.PENDENTE,
            origem_fluxo=Transferencia.Origem.AUDITORIA_DIVERGENCIA,
            aprovacao_admin_dispensada=True,
            motivo_dispensa_aprovacao=justificativa,
        )
        TransferenciaItem.objects.create(
            transferencia=transferencia,
            equipamento=equipamento,
            status='SELECIONADO',
        )
        equipamento.status = 'RESERVADO_TRANSFERENCIA'
        equipamento.save(update_fields=['status'])
        resolucao = AuditoriaResolucao.objects.create(
            divergencia=divergencia,
            tipo=AuditoriaResolucao.Tipo.TRANSFERIR,
            justificativa=justificativa,
            base_anterior=equipamento.regional,
            nova_base=base_destino,
            transferencia=transferencia,
            resolvida_por=usuario,
        )
        divergencia.status = AuditoriaDivergencia.Status.AGUARDANDO_TRANSFERENCIA
        divergencia.save(update_fields=['status'])
        if divergencia.auditoria_base.status != AuditoriaBase.Status.EM_REGULARIZACAO:
            divergencia.auditoria_base.status = AuditoriaBase.Status.EM_REGULARIZACAO
            divergencia.auditoria_base.save(update_fields=['status'])
        detalhes = {
            'campanha_id': divergencia.auditoria_base.campanha_id,
            'auditoria_base_id': divergencia.auditoria_base_id,
            'divergencia_id': divergencia.pk,
            'base_esperada_id': divergencia.base_esperada_id,
            'base_encontrada_id': divergencia.base_encontrada_id,
            'base_anterior_id': equipamento.regional_id,
            'nova_base_id': base_destino.pk,
            'transferencia_id': transferencia.pk,
            'justificativa': justificativa,
        }
        Historico.objects.create(
            equipamento=equipamento,
            tipo_acao='AUDITORIA_TRANSFERENCIA',
            usuario=usuario,
            detalhes=detalhes,
        )
        AuditoriaEvento.objects.create(
            auditoria_base=divergencia.auditoria_base,
            divergencia=divergencia,
            tipo='TRANSFERENCIA_CRIADA',
            usuario=usuario,
            dados=detalhes,
        )
        transaction.on_commit(
            lambda: ComunicadoService.auditoria_transferencia_criada(divergencia, transferencia, usuario)
        )
        from ordens_servico.services import OrdemServicoService
        OrdemServicoService.para_transferencia(transferencia, usuario)
        return transferencia
