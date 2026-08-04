from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from estoque.models import Equipamento, Historico, Transferencia
from estoque.services.comunicado_service import ComunicadoService

from auditorias.models import AuditoriaBase, AuditoriaDivergencia, AuditoriaEvento, AuditoriaResolucao
from auditorias.permissions import exigir_acesso_base


class RegularizacaoService:
    @staticmethod
    @transaction.atomic
    def manter_na_base(*, divergencia, usuario, justificativa):
        if not justificativa.strip():
            raise ValidationError('Informe uma justificativa.')
        divergencia = AuditoriaDivergencia.objects.select_for_update(of=('self',)).select_related(
            'auditoria_base__campanha', 'base_encontrada', 'base_esperada'
        ).get(pk=divergencia.pk)
        if (
            divergencia.auditoria_base.status != AuditoriaBase.Status.EM_REGULARIZACAO
            or not divergencia.auditoria_base.prazo_correcao_em
            or timezone.now() > divergencia.auditoria_base.prazo_correcao_em
        ):
            raise ValidationError('A auditoria não está dentro do prazo de correção.')
        if divergencia.tipo != AuditoriaDivergencia.Tipo.OUTRA_BASE:
            raise ValidationError('Esta divergência não permite alteração direta de base.')
        if divergencia.status not in (
            AuditoriaDivergencia.Status.ABERTA,
            AuditoriaDivergencia.Status.EM_ANALISE,
        ):
            raise ValidationError('A divergência não está disponível para regularização.')
        if not divergencia.equipamento_id or not divergencia.base_encontrada_id:
            raise ValidationError('A divergência não possui equipamento e base identificados.')
        exigir_acesso_base(usuario, divergencia.base_encontrada)
        equipamento = Equipamento.objects.select_for_update().get(pk=divergencia.equipamento_id)
        if Transferencia.objects.filter(
            itens__equipamento=equipamento,
            status__in=[Transferencia.Status.PENDENTE, Transferencia.Status.EM_TRANSITO],
        ).exists():
            raise ValidationError('O equipamento possui uma transferência aberta.')
        if hasattr(divergencia, 'resolucao'):
            raise ValidationError('Esta divergência já foi regularizada.')

        base_anterior = equipamento.regional
        equipamento.regional = divergencia.base_encontrada
        equipamento.save(update_fields=['regional'])
        resolucao = AuditoriaResolucao.objects.create(
            divergencia=divergencia,
            tipo=AuditoriaResolucao.Tipo.MANTER_NA_BASE,
            justificativa=justificativa,
            base_anterior=base_anterior,
            nova_base=divergencia.base_encontrada,
            resolvida_por=usuario,
        )
        divergencia.status = AuditoriaDivergencia.Status.RESOLVIDA
        divergencia.resolvida_em = timezone.now()
        divergencia.save(update_fields=['status', 'resolvida_em'])
        if divergencia.auditoria_base.status != AuditoriaBase.Status.EM_REGULARIZACAO:
            divergencia.auditoria_base.status = AuditoriaBase.Status.EM_REGULARIZACAO
            divergencia.auditoria_base.save(update_fields=['status'])
        detalhes = {
            'campanha_id': divergencia.auditoria_base.campanha_id,
            'auditoria_base_id': divergencia.auditoria_base_id,
            'divergencia_id': divergencia.pk,
            'base_esperada_id': divergencia.base_esperada_id,
            'base_encontrada_id': divergencia.base_encontrada_id,
            'base_anterior_id': base_anterior.pk,
            'nova_base_id': divergencia.base_encontrada_id,
            'transferencia_id': None,
            'justificativa': justificativa,
        }
        Historico.objects.create(
            equipamento=equipamento,
            tipo_acao='AUDITORIA_BASE_ATUALIZADA',
            usuario=usuario,
            detalhes=detalhes,
        )
        AuditoriaEvento.objects.create(
            auditoria_base=divergencia.auditoria_base,
            divergencia=divergencia,
            tipo='EQUIPAMENTO_MANTIDO_NA_BASE',
            usuario=usuario,
            dados=detalhes,
        )
        transaction.on_commit(
            lambda: ComunicadoService.auditoria_equipamento_mantido(divergencia, resolucao, usuario)
        )
        return resolucao

    @staticmethod
    def transferir(*, divergencia, base_destino, usuario, justificativa):
        from estoque.services.transferencia_service import TransferenciaService
        return TransferenciaService.criar_por_divergencia(
            divergencia=divergencia,
            base_destino=base_destino,
            usuario=usuario,
            justificativa=justificativa,
        )
