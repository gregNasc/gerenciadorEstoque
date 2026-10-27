from uuid import uuid4

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from estoque.services.comunicado_service import ComunicadoService
from insumos.models import (
    EventoSolicitacaoInsumo,
    Insumo,
    ItemSolicitacaoInsumo,
    SolicitacaoInsumo,
)


class SolicitacaoService:
    @staticmethod
    def registrar_evento(
        *, solicitacao, tipo, autor=None, status_anterior='', status_novo='',
        descricao='', dados=None, ocorrido_em=None,
    ):
        valores = {
            'solicitacao': solicitacao,
            'tipo': tipo,
            'autor': autor,
            'status_anterior': status_anterior,
            'status_novo': status_novo,
            'descricao': descricao,
            'dados': dados or {},
        }
        if ocorrido_em is not None:
            valores['ocorrido_em'] = ocorrido_em
        return EventoSolicitacaoInsumo.objects.create(**valores)

    @staticmethod
    def _construir_item(*, solicitacao, dados):
        insumo = dados.get('insumo')
        tipo = dados.get('tipo')
        if not tipo and insumo is not None:
            tipo = (
                ItemSolicitacaoInsumo.Tipo.EPI
                if insumo.natureza == Insumo.Natureza.EPI
                else ItemSolicitacaoInsumo.Tipo.INSUMO
            )
        tipo = tipo or ItemSolicitacaoInsumo.Tipo.NOVO_ITEM
        produto = dados.get('produto_equipamento')

        if tipo == ItemSolicitacaoInsumo.Tipo.EQUIPAMENTO:
            from compras.models import CatalogoProdutoEmpresa
            if not produto or not CatalogoProdutoEmpresa.objects.filter(
                empresa=solicitacao.base.empresa,
                produto=produto,
                ativo=True,
            ).exists():
                raise ValueError(
                    'O equipamento não está ativo no catálogo da empresa solicitante.'
                )

        item = ItemSolicitacaoInsumo(
            solicitacao=solicitacao,
            tipo=tipo,
            insumo=insumo,
            produto_equipamento=produto,
            descricao_novo_item=dados.get('descricao_novo_item', ''),
            especificacao=dados.get('especificacao', ''),
            justificativa_item=dados.get('justificativa_item', ''),
            anexo=dados.get('anexo'),
            quantidade=dados['quantidade'],
            observacao=dados.get('observacao', ''),
        )
        item.full_clean()
        return item

    @staticmethod
    def gerar_protocolo():
        data = timezone.localdate().strftime('%y%m%d')
        while True:
            protocolo = f'INS-{data}-{uuid4().hex[:6].upper()}'
            if not SolicitacaoInsumo.objects.filter(protocolo=protocolo).exists():
                return protocolo

    @staticmethod
    @transaction.atomic
    def resolver_novo_item(
        *, item, usuario, insumo=None, produto=None, observacao='',
    ):
        if item.tipo != ItemSolicitacaoInsumo.Tipo.NOVO_ITEM:
            raise ValueError('Somente itens solicitados como Novo item podem ser vinculados.')
        if bool(insumo) == bool(produto):
            raise ValueError('Selecione exatamente uma referência de catálogo.')
        solicitacao = item.solicitacao
        if solicitacao.status in {'REPROVADA', 'FINALIZADA'}:
            raise ValueError('Esta solicitação não aceita novas vinculações.')

        if insumo is not None:
            from compras.models import CodigoCatalogo
            from insumos.models import MovimentacaoInsumo, SaldoInsumoBase
            disponivel = (
                SaldoInsumoBase.objects.filter(
                    base=solicitacao.base, insumo=insumo,
                ).exists()
                or MovimentacaoInsumo.objects.filter(
                    base=solicitacao.base, insumo=insumo,
                ).exists()
                or CodigoCatalogo.objects.filter(
                    empresa=solicitacao.base.empresa,
                    insumo=insumo,
                    ativo=True,
                ).exists()
            )
            if not insumo.ativo or not disponivel:
                raise ValueError('O insumo não pertence ao catálogo desta empresa/Base.')
        if produto is not None:
            from compras.models import CatalogoProdutoEmpresa
            if not produto.ativo or not CatalogoProdutoEmpresa.objects.filter(
                empresa=solicitacao.base.empresa,
                produto=produto,
                ativo=True,
            ).exists():
                raise ValueError('O equipamento não pertence ao catálogo desta empresa.')

        item.resolvido_insumo = insumo
        item.resolvido_produto = produto
        item.resolvido_por = usuario
        item.resolvido_em = timezone.now()
        item.full_clean()
        item.save(update_fields=[
            'resolvido_insumo', 'resolvido_produto', 'resolvido_por',
            'resolvido_em',
        ])
        referencia = insumo or produto
        SolicitacaoService.registrar_evento(
            solicitacao=solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.ITEM_VINCULADO,
            autor=usuario,
            status_anterior=solicitacao.status,
            status_novo=solicitacao.status,
            descricao=observacao.strip() or (
                f'{item.descricao_novo_item} vinculado a {referencia}.'
            ),
            dados={
                'item_id': item.pk,
                'referencia_tipo': 'INSUMO' if insumo else 'EQUIPAMENTO',
                'referencia_id': referencia.pk,
            },
        )
        return item

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
        itens_modelo = [
            SolicitacaoService._construir_item(
                solicitacao=solicitacao,
                dados=dados_item,
            )
            for dados_item in itens
        ]
        for item in itens_modelo:
            item.save()
        SolicitacaoService.registrar_evento(
            solicitacao=solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.CRIADA,
            autor=solicitante,
            status_novo=solicitacao.status,
            descricao='Solicitação criada e enviada para acompanhamento.',
        )
        ComunicadoService.solicitacao_insumo_criada(solicitacao, solicitante)
        return solicitacao

    @staticmethod
    @transaction.atomic
    def receber_compras(*, solicitacao, usuario, observacao=''):
        if solicitacao.status != 'PENDENTE':
            raise ValueError('Somente solicitações aguardando Compras podem ser recebidas.')
        status_anterior = solicitacao.status
        solicitacao.status = 'RECEBIDA_COMPRAS'
        solicitacao.save(update_fields=['status'])
        SolicitacaoService.registrar_evento(
            solicitacao=solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.RECEBIDA_COMPRAS,
            autor=usuario,
            status_anterior=status_anterior,
            status_novo=solicitacao.status,
            descricao=observacao.strip(),
        )
        return solicitacao

    @staticmethod
    @transaction.atomic
    def iniciar_analise(*, solicitacao, usuario, observacao=''):
        if solicitacao.status != 'RECEBIDA_COMPRAS':
            raise ValueError('Somente solicitações recebidas podem entrar em análise.')
        status_anterior = solicitacao.status
        solicitacao.status = 'EM_ANALISE'
        solicitacao.save(update_fields=['status'])
        SolicitacaoService.registrar_evento(
            solicitacao=solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.EM_ANALISE,
            autor=usuario,
            status_anterior=status_anterior,
            status_novo=solicitacao.status,
            descricao=observacao.strip(),
        )
        return solicitacao

    @staticmethod
    def _garantir_em_analise(*, solicitacao, usuario):
        # Compatibilidade com integrações/solicitações anteriores à R6.
        if solicitacao.status == 'PENDENTE':
            SolicitacaoService.receber_compras(
                solicitacao=solicitacao, usuario=usuario,
            )
        if solicitacao.status == 'RECEBIDA_COMPRAS':
            SolicitacaoService.iniciar_analise(
                solicitacao=solicitacao, usuario=usuario,
            )

    @staticmethod
    @transaction.atomic
    def aprovar(*, solicitacao, usuario, observacao=''):
        SolicitacaoService._garantir_em_analise(
            solicitacao=solicitacao, usuario=usuario,
        )
        if solicitacao.status != 'EM_ANALISE':
            raise ValueError('Somente solicitações em análise podem ser aprovadas.')
        if solicitacao.itens.filter(
            tipo=ItemSolicitacaoInsumo.Tipo.NOVO_ITEM,
            resolvido_insumo__isnull=True,
            resolvido_produto__isnull=True,
        ).exists():
            raise ValueError(
                'Vincule todos os Novos itens ao catálogo antes de aprovar.'
            )

        status_anterior = solicitacao.status
        solicitacao.status = 'APROVADA'
        solicitacao.aprovado_por = usuario
        solicitacao.aprovado_em = timezone.now()
        solicitacao.observacao_aprovacao = observacao
        solicitacao.save(update_fields=[
            'status', 'aprovado_por', 'aprovado_em', 'observacao_aprovacao',
        ])
        SolicitacaoService.registrar_evento(
            solicitacao=solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.APROVADA,
            autor=usuario,
            status_anterior=status_anterior,
            status_novo=solicitacao.status,
            descricao=observacao.strip(),
        )
        ComunicadoService.solicitacao_insumo_decidida(solicitacao, usuario)
        return solicitacao

    @staticmethod
    @transaction.atomic
    def reprovar(*, solicitacao, usuario, motivo):
        SolicitacaoService._garantir_em_analise(
            solicitacao=solicitacao, usuario=usuario,
        )
        if solicitacao.status != 'EM_ANALISE':
            raise ValueError('Somente solicitações em análise podem ser reprovadas.')
        if not motivo.strip():
            raise ValueError('Informe o motivo da reprovação.')

        status_anterior = solicitacao.status
        solicitacao.status = 'REPROVADA'
        solicitacao.aprovado_por = usuario
        solicitacao.aprovado_em = timezone.now()
        solicitacao.observacao_aprovacao = motivo.strip()
        solicitacao.save(update_fields=[
            'status', 'aprovado_por', 'aprovado_em', 'observacao_aprovacao',
        ])
        SolicitacaoService.registrar_evento(
            solicitacao=solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.REPROVADA,
            autor=usuario,
            status_anterior=status_anterior,
            status_novo=solicitacao.status,
            descricao=motivo.strip(),
        )
        ComunicadoService.solicitacao_insumo_decidida(solicitacao, usuario)
        return solicitacao

    @staticmethod
    @transaction.atomic
    def colocar_em_compra(*, solicitacao, usuario, observacao=''):
        if solicitacao.status != 'APROVADA':
            raise ValueError('Somente solicitações aprovadas podem entrar em compra.')

        status_anterior = solicitacao.status
        solicitacao.status = 'PEDIDO_REALIZADO'
        solicitacao.em_compra_por = usuario
        solicitacao.em_compra_em = timezone.now()
        if observacao.strip():
            solicitacao.observacao_aprovacao = observacao.strip()
        solicitacao.save(update_fields=[
            'status', 'em_compra_por', 'em_compra_em', 'observacao_aprovacao',
        ])
        SolicitacaoService.registrar_evento(
            solicitacao=solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.PEDIDO_REALIZADO,
            autor=usuario,
            status_anterior=status_anterior,
            status_novo=solicitacao.status,
            descricao=observacao.strip(),
        )
        ComunicadoService.solicitacao_insumo_decidida(solicitacao, usuario)
        from ordens_servico.services import OrdemServicoService
        OrdemServicoService.para_solicitacao_insumo(solicitacao, usuario)
        return solicitacao

    @staticmethod
    @transaction.atomic
    def registrar_recebimento(*, solicitacao, usuario, observacao=''):
        if solicitacao.status not in {'PEDIDO_REALIZADO', 'EM_COMPRA'}:
            raise ValueError('Somente pedidos realizados podem ser recebidos.')
        status_anterior = solicitacao.status
        solicitacao.status = 'RECEBIDA'
        solicitacao.save(update_fields=['status'])
        SolicitacaoService.registrar_evento(
            solicitacao=solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.RECEBIDA,
            autor=usuario,
            status_anterior=status_anterior,
            status_novo=solicitacao.status,
            descricao=observacao.strip(),
        )
        return solicitacao

    @staticmethod
    @transaction.atomic
    def finalizar(*, solicitacao, usuario, observacao=''):
        if solicitacao.status in {'EM_COMPRA', 'PEDIDO_REALIZADO'}:
            SolicitacaoService.registrar_recebimento(
                solicitacao=solicitacao,
                usuario=usuario,
                observacao='Recebimento registrado durante a finalização de legado.',
            )
        if solicitacao.status != 'RECEBIDA':
            raise ValueError(
                'Somente solicitações recebidas podem ser atendidas.'
            )

        observacao = observacao.strip()
        if observacao:
            solicitacao.observacao_aprovacao = '\n'.join(filter(None, [
                solicitacao.observacao_aprovacao.strip(),
                f'Finalização: {observacao}',
            ]))

        status_anterior = solicitacao.status
        solicitacao.status = 'FINALIZADA'
        solicitacao.finalizado_por = usuario
        solicitacao.finalizado_em = timezone.now()
        solicitacao.save(update_fields=[
            'status', 'finalizado_por', 'finalizado_em',
            'observacao_aprovacao',
        ])
        solicitacao.itens.update(quantidade_atendida=F('quantidade'))
        SolicitacaoService.registrar_evento(
            solicitacao=solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.ATENDIDA,
            autor=usuario,
            status_anterior=status_anterior,
            status_novo=solicitacao.status,
            descricao=observacao,
        )
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
