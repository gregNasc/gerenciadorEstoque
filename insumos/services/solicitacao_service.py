from uuid import uuid4

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from estoque.services.comunicado_service import ComunicadoService
from insumos.models import ItemSolicitacaoInsumo, SolicitacaoInsumo


class SolicitacaoService:
    @staticmethod
    def gerar_protocolo():
        data = timezone.localdate().strftime('%y%m%d')
        while True:
            protocolo = f'INS-{data}-{uuid4().hex[:6].upper()}'
            if not SolicitacaoInsumo.objects.filter(protocolo=protocolo).exists():
                return protocolo

    @staticmethod
    @transaction.atomic
    def criar_solicitacao(*, base, solicitante, justificativa, prioridade, itens):
        if not itens:
            raise ValueError('Inclua ao menos um item na solicitação.')

        solicitacao = SolicitacaoInsumo.objects.create(
            protocolo=SolicitacaoService.gerar_protocolo(),
            base=base,
            solicitante=solicitante,
            justificativa=justificativa,
            prioridade=prioridade,
        )
        ItemSolicitacaoInsumo.objects.bulk_create([
            ItemSolicitacaoInsumo(
                solicitacao=solicitacao,
                insumo=item['insumo'],
                quantidade=item['quantidade'],
                observacao=item.get('observacao', ''),
            )
            for item in itens
        ])
        ComunicadoService.solicitacao_insumo_criada(solicitacao, solicitante)
        return solicitacao

    @staticmethod
    @transaction.atomic
    def aprovar(*, solicitacao, usuario, observacao=''):
        if solicitacao.status != 'PENDENTE':
            raise ValueError('Somente solicitações pendentes podem ser aprovadas.')

        solicitacao.status = 'APROVADA'
        solicitacao.aprovado_por = usuario
        solicitacao.aprovado_em = timezone.now()
        solicitacao.observacao_aprovacao = observacao
        solicitacao.save(update_fields=[
            'status', 'aprovado_por', 'aprovado_em', 'observacao_aprovacao',
        ])
        ComunicadoService.solicitacao_insumo_decidida(solicitacao, usuario)
        return solicitacao

    @staticmethod
    @transaction.atomic
    def reprovar(*, solicitacao, usuario, motivo):
        if solicitacao.status != 'PENDENTE':
            raise ValueError('Somente solicitações pendentes podem ser reprovadas.')
        if not motivo.strip():
            raise ValueError('Informe o motivo da reprovação.')

        solicitacao.status = 'REPROVADA'
        solicitacao.aprovado_por = usuario
        solicitacao.aprovado_em = timezone.now()
        solicitacao.observacao_aprovacao = motivo.strip()
        solicitacao.save(update_fields=[
            'status', 'aprovado_por', 'aprovado_em', 'observacao_aprovacao',
        ])
        ComunicadoService.solicitacao_insumo_decidida(solicitacao, usuario)
        return solicitacao

    @staticmethod
    @transaction.atomic
    def colocar_em_compra(*, solicitacao, usuario, observacao=''):
        if solicitacao.status != 'APROVADA':
            raise ValueError('Somente solicitações aprovadas podem entrar em compra.')

        solicitacao.status = 'EM_COMPRA'
        solicitacao.em_compra_por = usuario
        solicitacao.em_compra_em = timezone.now()
        if observacao.strip():
            solicitacao.observacao_aprovacao = observacao.strip()
        solicitacao.save(update_fields=[
            'status', 'em_compra_por', 'em_compra_em', 'observacao_aprovacao',
        ])
        ComunicadoService.solicitacao_insumo_decidida(solicitacao, usuario)
        from ordens_servico.services import OrdemServicoService
        OrdemServicoService.para_solicitacao_insumo(solicitacao, usuario)
        return solicitacao

    @staticmethod
    @transaction.atomic
    def finalizar(*, solicitacao, usuario, observacao=''):
        if solicitacao.status != 'EM_COMPRA':
            raise ValueError(
                'Somente solicitações em compra podem ser finalizadas.'
            )

        observacao = observacao.strip()
        if observacao:
            solicitacao.observacao_aprovacao = '\n'.join(filter(None, [
                solicitacao.observacao_aprovacao.strip(),
                f'Finalização: {observacao}',
            ]))

        solicitacao.status = 'FINALIZADA'
        solicitacao.finalizado_por = usuario
        solicitacao.finalizado_em = timezone.now()
        solicitacao.save(update_fields=[
            'status', 'finalizado_por', 'finalizado_em',
            'observacao_aprovacao',
        ])
        solicitacao.itens.update(quantidade_atendida=F('quantidade'))
        ComunicadoService.solicitacao_insumo_decidida(solicitacao, usuario)
        from ordens_servico.models import OrdemServico
        from ordens_servico.services import OrdemServicoService
        ordem = OrdemServicoService.para_solicitacao_insumo(solicitacao, usuario)
        OrdemServicoService.registrar_transicao(
            ordem,
            status=OrdemServico.Status.CONCLUIDA,
            usuario=usuario,
            evento='SOLICITACAO_INSUMO_FINALIZADA',
            dados={'protocolo': solicitacao.protocolo},
        )
        return solicitacao
