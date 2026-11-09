from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from compras.models import (
    Aquisicao,
    CapacidadeCatalogoProdutoEmpresa,
    CatalogoProdutoEmpresa,
    DivergenciaRecebimentoCompra,
    EventoCompra,
    FornecedorEmpresa,
    HistoricoPrecoProduto,
    HistoricoValorEquipamento,
    ItemAquisicao,
    ItemCotacaoFornecedor,
    ItemRemessaCompra,
    LinhaRecebimentoRemessa,
    ProcessoCotacao,
    RecebimentoRemessa,
    RemessaCompra,
    CotacaoFornecedor,
    VinculoEquipamentoAquisicao,
)
from compras.eventos import EventoCompraTipo
from compras.policies import AquisicaoAccessPolicy
from estoque.models import Base, Equipamento, Historico, Produto
from estoque.policies.compras import ComprasAccessPolicy
from estoque.security import secure_base_queryset
from estoque.services.ativo_capacidade_service import AtivoCapacidadeService
from estoque.services.comunicado_service import ComunicadoService
from insumos.models import (
    EventoSolicitacaoInsumo,
    ItemSolicitacaoInsumo,
    SaldoInsumoBase,
    SolicitacaoInsumo,
)
from insumos.policies import InsumosTenantPolicy
from insumos.services.movimentacao_service import MovimentacaoService
from insumos.services.saldo_service import SaldoInsumoService


class ProdutoPrecoService:
    @staticmethod
    def _origem_produto(origem):
        mapa = {
            Equipamento.OrigemValor.DOCUMENTO_COMPRA: Produto.OrigemPreco.DOCUMENTO_COMPRA,
            Equipamento.OrigemValor.INFORMADO_COMPRAS: Produto.OrigemPreco.INFORMADO_COMPRAS,
            Equipamento.OrigemValor.ESTIMATIVA_MERCADO: Produto.OrigemPreco.ESTIMATIVA_MERCADO,
            Equipamento.OrigemValor.LEGADO_SEM_DOCUMENTO: Produto.OrigemPreco.LEGADO,
            Equipamento.OrigemValor.SEM_PRECO_VALIDADO: Produto.OrigemPreco.SEM_PRECO_VALIDADO,
        }
        return mapa.get(origem, origem)

    @classmethod
    @transaction.atomic
    def definir(
        cls, *, produto, usuario, valor, origem, empresa=None, fonte='', fornecedor=None,
        observacao='', somente_inicial=False, comunicar=True,
    ):
        produto = Produto.objects.select_for_update().get(pk=produto.pk)
        perfil = getattr(usuario, 'perfil', None)
        empresa = empresa or getattr(perfil, 'empresa', None)
        if empresa is None:
            raise ValidationError('Informe a empresa do preço de referência.')
        if not ComprasAccessPolicy.empresas(
            usuario,
            action=ComprasAccessPolicy.EDIT,
            resource=ComprasAccessPolicy.CATALOGO,
        ).filter(pk=empresa.pk).exists():
            raise PermissionDenied('Empresa fora do escopo de precificação.')
        catalogo, _ = CatalogoProdutoEmpresa.objects.select_for_update().get_or_create(
            empresa=empresa,
            produto=produto,
            defaults={
                'ativo': True,
                'configurado_por': usuario,
                'preco_referencia': produto.preco_referencia,
                'preco_origem': produto.preco_origem,
                'preco_fonte': produto.preco_fonte,
                'preco_fornecedor': produto.preco_fornecedor,
                'preco_validado_por': produto.preco_validado_por,
                'preco_validado_em': produto.preco_validado_em,
            },
        )
        valor = Decimal(str(valor))
        if valor < 0:
            raise ValidationError('O preço de referência não pode ser negativo.')
        inicial = catalogo.preco_referencia is None
        if somente_inicial and not inicial:
            raise ValidationError('O produto já possui preço; use a ação específica de alteração.')
        permitido = (
            ComprasAccessPolicy.pode_definir_preco_produto(usuario)
            if inicial else ComprasAccessPolicy.pode_alterar_preco_produto(usuario)
        )
        if (
            ComprasAccessPolicy.restrito(usuario)
            or not permitido
        ):
            raise PermissionDenied('Sem permissão para definir ou alterar preços de produtos.')
        origem = cls._origem_produto(origem)
        if origem not in Produto.OrigemPreco.values:
            raise ValidationError('Origem do preço inválida.')
        fonte = str(fonte or '').strip()
        if (
            catalogo.preco_referencia == valor
            and catalogo.preco_origem == origem
            and catalogo.preco_fonte == fonte
            and catalogo.preco_fornecedor_id == getattr(fornecedor, 'pk', None)
        ):
            return produto
        HistoricoPrecoProduto.objects.create(
            empresa=empresa,
            produto=produto,
            valor_anterior=catalogo.preco_referencia,
            valor_novo=valor,
            origem_anterior=catalogo.preco_origem,
            origem_nova=origem,
            fonte=fonte,
            fornecedor=fornecedor,
            observacao=str(observacao or '').strip(),
            alterado_por=usuario,
        )
        catalogo.preco_referencia = valor
        catalogo.preco_origem = origem
        catalogo.preco_fonte = fonte
        catalogo.preco_fornecedor = fornecedor
        catalogo.preco_validado_por = usuario
        catalogo.preco_validado_em = timezone.now()
        catalogo.save(update_fields=[
            'preco_referencia', 'preco_origem', 'preco_fonte', 'preco_fornecedor',
            'preco_validado_por', 'preco_validado_em', 'atualizado_em',
        ])
        origem_equipamento = (
            Equipamento.OrigemValor.LEGADO_SEM_DOCUMENTO
            if origem == Produto.OrigemPreco.LEGADO
            else origem
        )
        Equipamento.objects.filter(
            regional__empresa=empresa,
            produto=produto,
        ).update(
            preco_referencia=valor,
            origem_valor=origem_equipamento,
            fornecedor=fornecedor,
            valor_validado_por=usuario,
            valor_validado_em=catalogo.preco_validado_em,
            data_atualizacao=timezone.now(),
        )
        if comunicar:
            transaction.on_commit(lambda: ComunicadoService.criar_acao(
                titulo=f'Preço de referência de {produto.descricao} atualizado',
                mensagem='O preço do catálogo foi atualizado com histórico e rastreabilidade.',
                usuario=usuario,
                usuarios=ComprasAccessPolicy.admins_para_empresa(
                    empresa,
                    resource=ComprasAccessPolicy.CATALOGO,
                ),
                empresa=empresa,
                incluir_admins=False,
                dados={
                    'produto_id': produto.pk,
                    'empresa_id': empresa.pk,
                    'acao': 'PRECO_PRODUTO_ATUALIZADO',
                },
                url='/compras/valores/equipamentos/',
            ))
        return produto


class FornecedorEmpresaService:
    """Gerencia homologações sem alterar o fornecedor jurídico global."""

    @classmethod
    def queryset(cls, usuario, *, action=ComprasAccessPolicy.VIEW):
        if not ComprasAccessPolicy.pode_homologar_fornecedores(usuario):
            return FornecedorEmpresa.objects.none()
        empresas = ComprasAccessPolicy.empresas(usuario, action=action)
        return FornecedorEmpresa.objects.filter(
            empresa__in=empresas,
        ).select_related(
            'empresa', 'fornecedor', 'cadastrado_por', 'homologado_por',
        )

    @classmethod
    @transaction.atomic
    def registrar(
        cls, *, empresa, fornecedor, usuario, codigo_interno='', observacao='',
    ):
        if not ComprasAccessPolicy.pode_homologar_fornecedores(usuario):
            raise PermissionDenied('Sem permissão para homologar fornecedores.')
        if not ComprasAccessPolicy.empresas(
            usuario,
            action=ComprasAccessPolicy.EDIT,
        ).filter(pk=empresa.pk).exists():
            raise PermissionDenied('Empresa fora do escopo de Compras.')
        relacionamento, criado = FornecedorEmpresa.objects.select_for_update().get_or_create(
            empresa=empresa,
            fornecedor=fornecedor,
            defaults={
                'codigo_interno': str(codigo_interno or '').strip(),
                'observacao': str(observacao or '').strip(),
                'cadastrado_por': usuario,
            },
        )
        return relacionamento, criado

    @classmethod
    @transaction.atomic
    def alterar_status(cls, relacionamento, *, status, usuario, observacao=None):
        relacionamento = cls.queryset(
            usuario,
            action=ComprasAccessPolicy.EDIT,
        ).select_for_update(of=('self',)).filter(pk=relacionamento.pk).first()
        if relacionamento is None:
            raise PermissionDenied('Fornecedor fora do escopo da empresa.')
        if status not in FornecedorEmpresa.Status.values:
            raise ValidationError('Status de homologação inválido.')
        if (
            status == FornecedorEmpresa.Status.HOMOLOGADO
            and not relacionamento.fornecedor.ativo
        ):
            raise ValidationError('Um fornecedor inativo não pode ser homologado.')
        relacionamento.status = status
        if observacao is not None:
            relacionamento.observacao = str(observacao).strip()
        campos = ['status', 'observacao', 'atualizado_em']
        if status == FornecedorEmpresa.Status.HOMOLOGADO:
            relacionamento.homologado_por = usuario
            relacionamento.homologado_em = timezone.now()
            campos.extend(['homologado_por', 'homologado_em'])
        relacionamento.save(update_fields=campos)
        return relacionamento

    @classmethod
    def homologados(cls, usuario, *, empresa):
        return cls.queryset(usuario).filter(
            empresa=empresa,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            fornecedor__ativo=True,
        )


class CotacaoService:
    STATUS_SOLICITACAO_PERMITIDOS = {
        'PENDENTE', 'RECEBIDA_COMPRAS', 'EM_ANALISE', 'APROVADA',
    }

    @classmethod
    def queryset(cls, usuario, *, action=ComprasAccessPolicy.VIEW):
        if not ComprasAccessPolicy.pode_gerenciar_aquisicoes(usuario):
            return ProcessoCotacao.objects.none()
        return ProcessoCotacao.objects.filter(
            empresa__in=ComprasAccessPolicy.empresas(usuario, action=action),
        ).select_related(
            'solicitacao__base', 'empresa', 'criado_por', 'decidido_por',
            'proposta_escolhida__fornecedor_empresa__fornecedor',
        ).prefetch_related(
            'propostas__fornecedor_empresa__fornecedor',
            'propostas__itens__item_solicitacao__insumo',
            'propostas__itens__item_solicitacao__produto_equipamento',
        )

    @classmethod
    def _solicitacao_autorizada(cls, solicitacao, usuario, *, action):
        if not ComprasAccessPolicy.pode_gerenciar_aquisicoes(usuario):
            raise PermissionDenied('Sem permissão para gerenciar cotações.')
        return InsumosTenantPolicy.requests(
            usuario,
            SolicitacaoInsumo.objects.select_related('base__empresa'),
            action=action,
        ).filter(pk=solicitacao.pk).first()

    @classmethod
    @transaction.atomic
    def abrir(cls, *, solicitacao, usuario):
        solicitacao = cls._solicitacao_autorizada(
            solicitacao,
            usuario,
            action=ComprasAccessPolicy.EDIT,
        )
        if solicitacao is None:
            raise PermissionDenied('Solicitação fora do escopo de Compras.')
        solicitacao = SolicitacaoInsumo.objects.select_for_update().select_related(
            'base__empresa'
        ).get(pk=solicitacao.pk)
        if solicitacao.status not in cls.STATUS_SOLICITACAO_PERMITIDOS:
            raise ValidationError(
                'A cotação não pode ser aberta porque esta solicitação '
                'já foi encerrada ou seguiu para a etapa de compra.'
            )
        existente = ProcessoCotacao.objects.select_for_update().filter(
            solicitacao=solicitacao,
        ).first()
        if existente:
            return existente, False

        # Iniciar a cotação é a primeira ação de Compras para muitas
        # solicitações. Avançamos as etapas administrativas automaticamente,
        # preservando cada transição na linha do tempo auditável.
        if solicitacao.status in {'PENDENTE', 'RECEBIDA_COMPRAS'}:
            from insumos.services.solicitacao_service import SolicitacaoService

            if solicitacao.status == 'PENDENTE':
                SolicitacaoService.receber_compras(
                    solicitacao=solicitacao,
                    usuario=usuario,
                    observacao='Recebida automaticamente ao iniciar a cotação.',
                )
            SolicitacaoService.iniciar_analise(
                solicitacao=solicitacao,
                usuario=usuario,
                observacao='Análise iniciada automaticamente com a cotação.',
            )
        processo = ProcessoCotacao(
            solicitacao=solicitacao,
            empresa=solicitacao.base.empresa,
            criado_por=usuario,
        )
        processo.full_clean()
        processo.save()
        EventoSolicitacaoInsumo.objects.create(
            solicitacao=solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.COTACAO_ABERTA,
            autor=usuario,
            descricao='Processo de cotação aberto por Compras.',
            dados={'processo_cotacao_id': processo.pk},
        )
        return processo, True

    @classmethod
    @transaction.atomic
    def adicionar_proposta(
        cls, *, processo, fornecedor_empresa, usuario, itens, **dados,
    ):
        processo = cls.queryset(
            usuario,
            action=ComprasAccessPolicy.EDIT,
        ).select_for_update(of=('self',)).filter(pk=processo.pk).first()
        if processo is None:
            raise PermissionDenied('Cotação fora do escopo de Compras.')
        if processo.status in {
            ProcessoCotacao.Status.DECIDIDO,
            ProcessoCotacao.Status.CANCELADO,
        }:
            raise ValidationError('Esta cotação não aceita novas propostas.')
        fornecedor_empresa = FornecedorEmpresaService.queryset(
            usuario,
            action=ComprasAccessPolicy.EDIT,
        ).filter(
            pk=fornecedor_empresa.pk,
            empresa=processo.empresa,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
            fornecedor__ativo=True,
        ).first()
        if fornecedor_empresa is None:
            raise ValidationError('Selecione um fornecedor homologado e ativo.')
        if not itens:
            raise ValidationError('Inclua ao menos um item na proposta.')
        if CotacaoFornecedor.objects.filter(
            processo=processo,
            fornecedor_empresa=fornecedor_empresa,
        ).exists():
            raise ValidationError('Este fornecedor já possui proposta na cotação.')
        proposta = CotacaoFornecedor(
            processo=processo,
            fornecedor_empresa=fornecedor_empresa,
            cadastrado_por=usuario,
            **dados,
        )
        proposta.full_clean()
        proposta.save()
        itens_validos = {
            item.pk: item
            for item in ItemSolicitacaoInsumo.objects.filter(
                solicitacao=processo.solicitacao,
            )
        }
        for dados_item in itens:
            item_solicitacao = dados_item.get('item_solicitacao')
            if getattr(item_solicitacao, 'pk', None) not in itens_validos:
                raise ValidationError('Um item não pertence à solicitação cotada.')
            item = ItemCotacaoFornecedor(cotacao=proposta, **dados_item)
            item.full_clean()
            item.save()
        processo.status = ProcessoCotacao.Status.EM_ANALISE
        processo.save(update_fields=['status', 'atualizado_em'])
        EventoSolicitacaoInsumo.objects.create(
            solicitacao=processo.solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.PROPOSTA_RECEBIDA,
            autor=usuario,
            descricao='Proposta de fornecedor homologado registrada.',
            dados={
                'processo_cotacao_id': processo.pk,
                'proposta_id': proposta.pk,
                'fornecedor_empresa_id': fornecedor_empresa.pk,
            },
        )
        return proposta

    @classmethod
    @transaction.atomic
    def decidir(cls, *, processo, proposta, usuario, justificativa):
        processo = cls.queryset(
            usuario,
            action=ComprasAccessPolicy.APPROVE,
        ).select_for_update(of=('self',)).filter(pk=processo.pk).first()
        if processo is None:
            raise PermissionDenied('Cotação fora do escopo de decisão.')
        if processo.status == ProcessoCotacao.Status.DECIDIDO:
            raise ValidationError('Esta cotação já possui decisão registrada.')
        justificativa = str(justificativa or '').strip()
        if len(justificativa) < 10:
            raise ValidationError(
                'Informe uma justificativa clara para a escolha da proposta.'
            )
        proposta = CotacaoFornecedor.objects.select_for_update().filter(
            pk=proposta.pk,
            processo=processo,
            status=CotacaoFornecedor.Status.RECEBIDA,
        ).first()
        if proposta is None:
            raise ValidationError('A proposta selecionada não está disponível.')
        CotacaoFornecedor.objects.filter(
            processo=processo,
            status=CotacaoFornecedor.Status.RECEBIDA,
        ).exclude(pk=proposta.pk).update(
            status=CotacaoFornecedor.Status.NAO_SELECIONADA,
        )
        proposta.status = CotacaoFornecedor.Status.ESCOLHIDA
        proposta.save(update_fields=['status', 'atualizado_em'])
        processo.status = ProcessoCotacao.Status.DECIDIDO
        processo.proposta_escolhida = proposta
        processo.justificativa_decisao = justificativa
        processo.decidido_por = usuario
        processo.decidido_em = timezone.now()
        processo.save(update_fields=[
            'status', 'proposta_escolhida', 'justificativa_decisao',
            'decidido_por', 'decidido_em', 'atualizado_em',
        ])
        EventoSolicitacaoInsumo.objects.create(
            solicitacao=processo.solicitacao,
            tipo=EventoSolicitacaoInsumo.Tipo.COTACAO_DECIDIDA,
            autor=usuario,
            descricao='Decisão de cotação registrada com justificativa.',
            dados={
                'processo_cotacao_id': processo.pk,
                'proposta_id': proposta.pk,
                'fornecedor_empresa_id': proposta.fornecedor_empresa_id,
            },
        )
        return processo


class AquisicaoService:
    @staticmethod
    def _referencia_item_cotado(item_cotacao):
        solicitado = item_cotacao.item_solicitacao
        if solicitado.tipo in {
            ItemSolicitacaoInsumo.Tipo.INSUMO,
            ItemSolicitacaoInsumo.Tipo.EPI,
        }:
            return {
                'tipo_item': ItemAquisicao.Tipo.INSUMO,
                'insumo': solicitado.insumo,
                'produto': None,
            }
        if solicitado.tipo == ItemSolicitacaoInsumo.Tipo.EQUIPAMENTO:
            return {
                'tipo_item': ItemAquisicao.Tipo.EQUIPAMENTO,
                'produto': solicitado.produto_equipamento,
                'insumo': None,
            }
        if solicitado.tipo == ItemSolicitacaoInsumo.Tipo.NOVO_ITEM:
            if solicitado.resolvido_insumo_id:
                return {
                    'tipo_item': ItemAquisicao.Tipo.INSUMO,
                    'insumo': solicitado.resolvido_insumo,
                    'produto': None,
                }
            if solicitado.resolvido_produto_id:
                return {
                    'tipo_item': ItemAquisicao.Tipo.EQUIPAMENTO,
                    'produto': solicitado.resolvido_produto,
                    'insumo': None,
                }
            raise ValidationError(
                f'Vincule o item "{solicitado.descricao_exibicao}" ao catálogo antes da aquisição.'
            )
        raise ValidationError('A proposta contém um tipo de item não reconhecido.')

    @classmethod
    @transaction.atomic
    def criar_da_cotacao(
        cls, *, processo, usuario, numero_pedido_compra='', centro_custo='',
        observacao='',
    ):
        processo = CotacaoService.queryset(
            usuario,
            action=ComprasAccessPolicy.CREATE,
        ).select_for_update(of=('self',)).filter(pk=processo.pk).first()
        if processo is None:
            raise PermissionDenied('Cotação fora do escopo de Compras.')
        existente = Aquisicao.objects.select_for_update().filter(
            processo_cotacao=processo,
        ).first()
        if existente is not None:
            return existente, False
        if (
            processo.status != ProcessoCotacao.Status.DECIDIDO
            or not processo.proposta_escolhida_id
        ):
            raise ValidationError('Registre a decisão da cotação antes de gerar a aquisição.')
        if processo.solicitacao.status != 'APROVADA':
            raise ValidationError(
                'A solicitação precisa estar aprovada antes de gerar a aquisição.'
            )
        proposta = CotacaoFornecedor.objects.select_for_update().select_related(
            'fornecedor_empresa__fornecedor',
        ).prefetch_related(
            'itens__item_solicitacao__insumo',
            'itens__item_solicitacao__produto_equipamento',
            'itens__item_solicitacao__resolvido_insumo',
            'itens__item_solicitacao__resolvido_produto',
        ).get(pk=processo.proposta_escolhida_id)
        if proposta.status != CotacaoFornecedor.Status.ESCOLHIDA:
            raise ValidationError('A proposta escolhida não está disponível para aquisição.')
        relacionamento = proposta.fornecedor_empresa
        if (
            relacionamento.status != FornecedorEmpresa.Status.HOMOLOGADO
            or not relacionamento.fornecedor.ativo
        ):
            raise ValidationError(
                'O fornecedor escolhido precisa continuar homologado e ativo.'
            )
        itens = []
        for item_cotacao in proposta.itens.all():
            referencia = cls._referencia_item_cotado(item_cotacao)
            itens.append({
                **referencia,
                'item_cotacao_origem': item_cotacao,
                'quantidade': item_cotacao.quantidade,
                'valor_unitario': item_cotacao.valor_unitario,
                'desconto': Decimal('0'),
                'frete': Decimal('0'),
                'impostos': Decimal('0'),
                'observacao': item_cotacao.observacao,
            })
        if not itens:
            raise ValidationError('A proposta escolhida não possui itens.')
        aquisicao = cls.criar(
            empresa=processo.empresa,
            base_destino=processo.solicitacao.base,
            fornecedor=relacionamento.fornecedor,
            usuario=usuario,
            itens=itens,
            processo_cotacao=processo,
            proposta_origem=proposta,
            frete_cotacao=proposta.frete,
            impostos_cotacao=proposta.impostos,
            desconto_cotacao=proposta.desconto,
            numero_pedido_compra=str(numero_pedido_compra or '').strip(),
            centro_custo=str(centro_custo or '').strip(),
            observacao=str(observacao or '').strip(),
        )
        return aquisicao, True

    @classmethod
    @transaction.atomic
    def criar(cls, *, empresa, fornecedor, usuario, itens, **dados):
        if not AquisicaoAccessPolicy.pode_gerenciar(usuario):
            raise PermissionDenied('Sem permissão para gerenciar aquisições.')
        if not itens:
            raise ValidationError('Inclua ao menos um item na aquisição.')
        if not ComprasAccessPolicy.empresas(
            usuario,
            action=ComprasAccessPolicy.CREATE,
        ).filter(pk=empresa.pk).exists():
            raise PermissionDenied('Empresa fora do escopo corporativo de Compras.')
        if not FornecedorEmpresa.objects.filter(
            empresa=empresa,
            fornecedor=fornecedor,
            fornecedor__ativo=True,
            status=FornecedorEmpresa.Status.HOMOLOGADO,
        ).exists():
            raise ValidationError(
                'O fornecedor precisa estar homologado para esta empresa.'
            )
        arquivo_xml = dados.get('arquivo_xml_nfe')
        if arquivo_xml and hasattr(arquivo_xml, 'read'):
            from compras.nfe import LeitorNFe

            posicao = arquivo_xml.tell() if hasattr(arquivo_xml, 'tell') else 0
            conteudo_xml = arquivo_xml.read()
            if hasattr(arquivo_xml, 'seek'):
                arquivo_xml.seek(posicao)
            LeitorNFe.ler(conteudo_xml)
        aquisicao = Aquisicao(
            empresa=empresa, fornecedor=fornecedor, cadastrado_por=usuario, **dados
        )
        aquisicao.full_clean()
        aquisicao.save()
        for dados_item in itens:
            item = ItemAquisicao(aquisicao=aquisicao, **dados_item)
            item.full_clean()
            item.save()
        EventoCompra.objects.create(
            aquisicao=aquisicao,
            tipo=EventoCompraTipo.AQUISICAO_CRIADA,
            usuario=usuario,
            dados={
                'itens': len(itens),
                'processo_cotacao_id': aquisicao.processo_cotacao_id,
                'proposta_origem_id': aquisicao.proposta_origem_id,
            },
        )
        if aquisicao.arquivo_xml_nfe:
            from compras.nfe import NFeAquisicaoService

            NFeAquisicaoService.processar(
                aquisicao=aquisicao,
                usuario=usuario,
            )
        transaction.on_commit(lambda: ComunicadoService.criar_acao(
            titulo=f'Aquisicao #{aquisicao.pk} criada',
            mensagem=(
                f'Aquisicao registrada para {empresa.nome}, fornecedor '
                f'{fornecedor.nome}, com {len(itens)} item(ns).'
            ),
            usuario=usuario,
            usuarios=ComprasAccessPolicy.admins_para_empresa(empresa),
            empresa=empresa,
            incluir_admins=False,
            dados={
                'aquisicao_id': aquisicao.pk,
                'evento': EventoCompraTipo.AQUISICAO_CRIADA,
                'acao': 'CRIADA',
            },
            url=f'/compras/{aquisicao.pk}/',
        ))
        return aquisicao

    @classmethod
    @transaction.atomic
    def aprovar(cls, aquisicao, usuario):
        if not AquisicaoAccessPolicy.queryset(
            usuario,
            action=ComprasAccessPolicy.APPROVE,
        ).filter(pk=aquisicao.pk).exists():
            raise PermissionDenied('Sem permissão para aprovar a aquisição.')
        aquisicao = Aquisicao.objects.select_for_update(of=('self',)).select_related(
            'processo_cotacao__solicitacao',
        ).get(pk=aquisicao.pk)
        if aquisicao.status != Aquisicao.Status.RASCUNHO:
            raise ValidationError('Somente aquisições em rascunho podem ser aprovadas.')
        aquisicao.status = Aquisicao.Status.APROVADA
        aquisicao.aprovado_por = usuario
        aquisicao.aprovado_em = timezone.now()
        aquisicao.save(update_fields=['status', 'aprovado_por', 'aprovado_em', 'atualizado_em'])
        EventoCompra.objects.create(
            aquisicao=aquisicao,
            tipo=EventoCompraTipo.AQUISICAO_APROVADA,
            usuario=usuario,
        )
        if aquisicao.processo_cotacao_id:
            solicitacao = aquisicao.processo_cotacao.solicitacao
            if solicitacao.status == 'APROVADA':
                from insumos.services.solicitacao_service import SolicitacaoService
                SolicitacaoService.colocar_em_compra(
                    solicitacao=solicitacao,
                    usuario=usuario,
                    observacao=(
                        f'Aquisição #{aquisicao.pk} aprovada a partir da cotação.'
                    ),
                )
            elif solicitacao.status not in {'PEDIDO_REALIZADO', 'EM_COMPRA'}:
                raise ValidationError(
                    'A solicitação vinculada não está pronta para o pedido de compra.'
                )
        transaction.on_commit(lambda: ComunicadoService.criar_acao(
            titulo=f'Aquisicao #{aquisicao.pk} aprovada',
            mensagem=f'A aquisicao de {aquisicao.fornecedor.nome} foi aprovada.',
            usuario=usuario,
            usuarios=list(
                ComprasAccessPolicy.admins_para_empresa(aquisicao.empresa)
            ) + [aquisicao.cadastrado_por],
            empresa=aquisicao.empresa,
            incluir_admins=False,
            dados={
                'aquisicao_id': aquisicao.pk,
                'evento': EventoCompraTipo.AQUISICAO_APROVADA,
                'acao': 'APROVADA',
            },
            url=f'/compras/{aquisicao.pk}/',
        ))
        return aquisicao

    @classmethod
    @transaction.atomic
    def vincular_equipamento(cls, *, item, equipamento, usuario):
        item = ItemAquisicao.objects.select_for_update().select_related('aquisicao').get(pk=item.pk)
        if not AquisicaoAccessPolicy.queryset(
            usuario,
            action=ComprasAccessPolicy.EDIT,
        ).filter(pk=item.aquisicao_id).exists():
            raise PermissionDenied('Sem permissão para vincular equipamentos.')
        if not ComprasAccessPolicy.bases(
            usuario,
            action=ComprasAccessPolicy.EDIT,
        ).filter(pk=equipamento.regional_id).exists():
            raise PermissionDenied('Equipamento fora do escopo de Compras.')
        if item.tipo_item != ItemAquisicao.Tipo.EQUIPAMENTO:
            raise ValidationError('O item não é de equipamento.')
        if item.equipamentos_vinculados.count() >= int(item.quantidade):
            raise ValidationError('Todos os equipamentos previstos já foram vinculados.')
        vinculo = VinculoEquipamentoAquisicao(
            item=item, equipamento=equipamento,
            valor_aquisicao_snapshot=item.valor_unitario,
        )
        vinculo.full_clean()
        vinculo.save()
        cls.atualizar_valor_equipamento(
            equipamento=equipamento,
            usuario=usuario,
            custo=item.valor_unitario,
            referencia=equipamento.preco_referencia,
            origem=Equipamento.OrigemValor.DOCUMENTO_COMPRA,
            motivo=f'Vinculado à aquisição #{item.aquisicao_id}',
            fornecedor=item.aquisicao.fornecedor,
            documento=item.aquisicao.numero_documento,
            data_aquisicao=item.aquisicao.data_compra,
        )
        return vinculo

    @staticmethod
    @transaction.atomic
    def atualizar_valor_equipamento(
        *, equipamento, usuario, custo, referencia, origem, motivo,
        fornecedor=None, documento='', data_aquisicao=None,
    ):
        if not ComprasAccessPolicy.pode_editar_precos(usuario):
            raise PermissionDenied('Sem permissão para editar valores de equipamentos.')
        motivo = str(motivo or '').strip()
        if not motivo:
            raise ValidationError('Informe o motivo da alteração de valor.')
        equipamento = Equipamento.objects.select_for_update().get(pk=equipamento.pk)
        if not ComprasAccessPolicy.bases(
            usuario,
            action=ComprasAccessPolicy.EDIT,
        ).filter(pk=equipamento.regional_id).exists():
            raise PermissionDenied('Equipamento fora do escopo de Compras.')
        custo = Decimal(str(custo)) if custo not in (None, '') else None
        referencia = Decimal(str(referencia)) if referencia not in (None, '') else None
        if custo is not None and custo < 0 or referencia is not None and referencia < 0:
            raise ValidationError('Valores não podem ser negativos.')
        HistoricoValorEquipamento.objects.create(
            equipamento=equipamento,
            custo_anterior=equipamento.custo_aquisicao,
            custo_novo=custo,
            referencia_anterior=equipamento.preco_referencia,
            referencia_nova=referencia,
            origem_anterior=equipamento.origem_valor,
            origem_nova=origem,
            motivo=motivo,
            alterado_por=usuario,
        )
        equipamento.custo_aquisicao = custo
        equipamento.preco_referencia = referencia
        equipamento.origem_valor = origem
        equipamento.fornecedor = fornecedor or equipamento.fornecedor
        equipamento.documento_compra = documento or equipamento.documento_compra
        equipamento.data_aquisicao = data_aquisicao or equipamento.data_aquisicao
        equipamento.valor_validado_por = usuario
        equipamento.valor_validado_em = timezone.now()
        equipamento.save(update_fields=[
            'custo_aquisicao', 'preco_referencia', 'origem_valor', 'fornecedor',
            'documento_compra', 'data_aquisicao', 'valor_validado_por',
            'valor_validado_em', 'data_atualizacao',
        ])
        if equipamento.produto_id and referencia is not None:
            ProdutoPrecoService.definir(
                produto=equipamento.produto,
                usuario=usuario,
                empresa=equipamento.regional.empresa,
                valor=referencia,
                origem=origem,
                fonte=documento,
                fornecedor=fornecedor,
                observacao=motivo,
            )
        transaction.on_commit(lambda: ComunicadoService.criar_acao(
            titulo=f'Valor do equipamento {equipamento.codigo} atualizado',
            mensagem=f'O valor patrimonial foi atualizado. Motivo: {motivo}',
            usuario=usuario,
            usuarios=ComprasAccessPolicy.admins_para_empresa(
                equipamento.regional.empresa
            ),
            bases=[equipamento.regional],
            empresa=equipamento.regional.empresa,
            incluir_admins=False,
            dados={'equipamento_id': equipamento.pk, 'acao': 'VALOR_ATUALIZADO'},
            url='/compras/valores/equipamentos/',
        ))
        return equipamento

    @staticmethod
    @transaction.atomic
    def atualizar_valores_equipamentos_em_lote(*, itens, usuario):
        if not ComprasAccessPolicy.pode_importar_precos(usuario):
            raise PermissionDenied('Sem permissão para editar valores de equipamentos.')
        if not itens:
            return 0, 0

        ids = [item['equipamento_id'] for item in itens]
        equipamentos = {
            equipamento.pk: equipamento
            for equipamento in Equipamento.objects.select_for_update().select_related(
                'regional__empresa'
            ).filter(
                pk__in=ids,
                regional__in=ComprasAccessPolicy.bases(
                    usuario,
                    action=ComprasAccessPolicy.EDIT,
                ),
            )
        }
        ausentes = [equipamento_id for equipamento_id in ids if equipamento_id not in equipamentos]
        if ausentes:
            raise ValidationError(
                _('Há equipamentos inexistentes ou fora do escopo autorizado.')
            )

        agora = timezone.now()
        atualizados = []
        historicos = []
        ignorados = 0
        bases_ids = set()
        empresas = {}

        for item in itens:
            equipamento = equipamentos[item['equipamento_id']]
            try:
                custo = (
                    Decimal(str(item['custo']))
                    if item['custo'] not in (None, '') else None
                )
                referencia = (
                    Decimal(str(item['referencia']))
                    if item['referencia'] not in (None, '') else None
                )
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValidationError(
                    _('Linha %(numero)s: custo ou preço de referência inválido.') % {
                        'numero': item['linha'],
                    }
                ) from exc
            if custo is not None and custo < 0 or referencia is not None and referencia < 0:
                raise ValidationError(
                    _('Linha %(numero)s: valores não podem ser negativos.') % {
                        'numero': item['linha'],
                    }
                )

            origem = str(item['origem'] or '').strip().upper()
            if origem not in Equipamento.OrigemValor.values:
                raise ValidationError(
                    _('Linha %(numero)s: origem de valor inválida.') % {
                        'numero': item['linha'],
                    }
                )
            if (
                equipamento.custo_aquisicao == custo
                and equipamento.preco_referencia == referencia
                and equipamento.origem_valor == origem
            ):
                ignorados += 1
                continue

            motivo = str(item['motivo'] or '').strip().upper()
            if not motivo:
                raise ValidationError(
                    _('Linha %(numero)s: informe o motivo da precificação.') % {
                        'numero': item['linha'],
                    }
                )
            historicos.append(HistoricoValorEquipamento(
                equipamento=equipamento,
                custo_anterior=equipamento.custo_aquisicao,
                custo_novo=custo,
                referencia_anterior=equipamento.preco_referencia,
                referencia_nova=referencia,
                origem_anterior=equipamento.origem_valor,
                origem_nova=origem,
                motivo=motivo,
                alterado_por=usuario,
            ))
            equipamento.custo_aquisicao = custo
            equipamento.preco_referencia = referencia
            equipamento.origem_valor = origem
            equipamento.valor_validado_por = usuario
            equipamento.valor_validado_em = agora
            equipamento.data_atualizacao = agora
            atualizados.append(equipamento)
            bases_ids.add(equipamento.regional_id)
            empresas[equipamento.regional.empresa_id] = equipamento.regional.empresa

        if not atualizados:
            return 0, ignorados

        HistoricoValorEquipamento.objects.bulk_create(historicos)
        Equipamento.objects.bulk_update(atualizados, [
            'custo_aquisicao', 'preco_referencia', 'origem_valor',
            'valor_validado_por', 'valor_validado_em', 'data_atualizacao',
        ])
        referencias_por_produto = {}
        for equipamento in atualizados:
            if not equipamento.produto_id or equipamento.preco_referencia is None:
                continue
            atual = (equipamento.preco_referencia, equipamento.origem_valor)
            chave = (equipamento.regional.empresa_id, equipamento.produto_id)
            anterior = referencias_por_produto.get(chave)
            if anterior and anterior != atual:
                raise ValidationError(
                    'A planilha possui preços de referência conflitantes para o mesmo produto.'
                )
            referencias_por_produto[chave] = atual
        produtos = Produto.objects.in_bulk(
            {produto_id for _, produto_id in referencias_por_produto}
        )
        for (empresa_id, produto_id), (valor, origem) in referencias_por_produto.items():
            ProdutoPrecoService.definir(
                produto=produtos[produto_id],
                usuario=usuario,
                empresa=empresas[empresa_id],
                valor=valor,
                origem=origem,
                fonte='IMPORTAÇÃO XLSX',
                observacao='PRECIFICAÇÃO EM LOTE',
                comunicar=False,
            )
        atualizados_ids = [equipamento.pk for equipamento in atualizados]
        empresa = next(iter(empresas.values())) if len(empresas) == 1 else None
        quantidade = len(atualizados)
        transaction.on_commit(lambda: ComunicadoService.criar_acao(
            titulo=_('Valores de %(quantidade)s equipamentos atualizados') % {
                'quantidade': quantidade,
            },
            mensagem=_(
                'A importação de precificação atualizou %(quantidade)s equipamento(s) '
                'e ignorou %(ignorados)s linha(s) sem alteração.'
            ) % {'quantidade': quantidade, 'ignorados': ignorados},
            usuario=usuario,
            bases=list(bases_ids),
            empresa=empresa,
            usuarios=(
                ComprasAccessPolicy.admins_para_empresa(empresa)
                if empresa else None
            ),
            incluir_admins=False,
            dados={
                'equipamentos_ids': atualizados_ids,
                'quantidade': quantidade,
                'ignorados': ignorados,
                'acao': 'VALORES_ATUALIZADOS_EM_LOTE',
            },
            url='/compras/valores/equipamentos/',
        ))
        return quantidade, ignorados


class RemessaCompraService:
    @staticmethod
    def _comunicar(remessa, usuario, evento, titulo, mensagem):
        transaction.on_commit(lambda: ComunicadoService.criar_acao(
            titulo=titulo,
            mensagem=mensagem,
            usuario=usuario,
            usuarios=ComprasAccessPolicy.admins_para_empresa(remessa.empresa),
            bases=[remessa.base_destino],
            empresa=remessa.empresa,
            incluir_admins=False,
            dados={
                'remessa_id': remessa.pk,
                'protocolo': remessa.protocolo,
                'evento': evento,
            },
        ))

    @classmethod
    @transaction.atomic
    def criar(cls, *, empresa, fluxo, base_destino, usuario, itens, aquisicao=None, base_origem=None, **dados):
        if not ComprasAccessPolicy.pode_criar_remessa(usuario):
            raise PermissionDenied('Sem permissão para criar remessas.')
        if not itens:
            raise ValidationError('Inclua ao menos um item na remessa.')
        bases_permitidas = ComprasAccessPolicy.bases(
            usuario,
            action=ComprasAccessPolicy.CREATE,
        )
        if not ComprasAccessPolicy.empresas(
            usuario,
            action=ComprasAccessPolicy.CREATE,
        ).filter(pk=empresa.pk).exists():
            raise PermissionDenied('Empresa fora do escopo de Compras.')
        if not bases_permitidas.filter(pk=base_destino.pk).exists():
            raise PermissionDenied('Base de destino fora do escopo de Compras.')
        if base_origem and not bases_permitidas.filter(pk=base_origem.pk).exists():
            raise PermissionDenied('Base de origem fora do escopo de Compras.')
        if aquisicao and not AquisicaoAccessPolicy.queryset(
            usuario,
            action=ComprasAccessPolicy.CREATE,
        ).filter(pk=aquisicao.pk).exists():
            raise PermissionDenied('Aquisição fora do escopo de Compras.')
        remessa = RemessaCompra(
            empresa=empresa, fluxo=fluxo, base_destino=base_destino,
            base_origem=base_origem, aquisicao=aquisicao, criada_por=usuario, **dados,
        )
        remessa.full_clean()
        remessa.save()
        for dados_item in itens:
            item = ItemRemessaCompra(remessa=remessa, **dados_item)
            item.full_clean()
            if item.item_aquisicao_id:
                ja_planejado = ItemRemessaCompra.objects.filter(
                    item_aquisicao_id=item.item_aquisicao_id,
                ).aggregate(total=Sum('quantidade_prevista'))['total'] or Decimal('0')
                if ja_planejado + item.quantidade_prevista > item.item_aquisicao.quantidade:
                    raise ValidationError(
                        'A quantidade das remessas excede a quantidade da aquisição.'
                    )
            if item.item_nfe_id:
                ja_planejado_nfe = ItemRemessaCompra.objects.filter(
                    item_nfe_id=item.item_nfe_id,
                ).aggregate(total=Sum('quantidade_prevista'))['total'] or Decimal('0')
                if ja_planejado_nfe + item.quantidade_prevista > item.item_nfe.quantidade:
                    raise ValidationError(
                        'A quantidade das remessas excede a quantidade da NF-e.'
                    )
            if fluxo == RemessaCompra.Fluxo.ENTRE_BASES:
                if item.equipamento_id or item.produto_id:
                    raise ValidationError('Use a transferência existente para equipamentos entre bases.')
                saldo = SaldoInsumoService.bloquear(base_origem, item.insumo)
                disponivel = saldo.saldo - saldo.saldo_reservado
                if disponivel < item.quantidade_prevista:
                    raise ValidationError(
                        f'Estoque disponível insuficiente para {item.insumo}: {disponivel}.'
                    )
                saldo.saldo_reservado += item.quantidade_prevista
                saldo.save(update_fields=['saldo_reservado', 'recalculado_em'])
            item.save()
        EventoCompra.objects.create(
            remessa=remessa,
            tipo=EventoCompraTipo.REMESSA_CRIADA,
            usuario=usuario,
            dados={'fluxo': fluxo, 'itens': len(itens)},
        )
        cls._comunicar(
            remessa, usuario, EventoCompraTipo.REMESSA_CRIADA,
            f'Remessa {remessa.protocolo} criada',
            f'Uma remessa foi preparada para {base_destino.nome}.',
        )
        from ordens_servico.services import OrdemServicoService
        OrdemServicoService.para_remessa_compra(remessa, usuario)
        return remessa

    @classmethod
    @transaction.atomic
    def enviar(cls, remessa, usuario, codigo_rastreio=''):
        if not ComprasAccessPolicy.pode_criar_remessa(usuario):
            raise PermissionDenied('Sem permissão para enviar remessas.')
        remessa = RemessaCompra.objects.select_for_update().get(pk=remessa.pk)
        if not AquisicaoAccessPolicy.remessas(
            usuario,
            action=ComprasAccessPolicy.EDIT,
        ).filter(pk=remessa.pk).exists():
            raise PermissionDenied('Remessa fora do escopo de Compras.')
        if remessa.status != RemessaCompra.Status.PREPARADA:
            raise ValidationError('Somente remessas preparadas podem ser enviadas.')
        remessa.status = RemessaCompra.Status.AGUARDANDO_CONFERENCIA
        remessa.enviada_por = usuario
        remessa.enviada_em = timezone.now()
        remessa.codigo_rastreio = str(codigo_rastreio or '').strip()
        remessa.save(update_fields=[
            'status', 'enviada_por', 'enviada_em', 'codigo_rastreio', 'atualizada_em',
        ])
        equipamentos = Equipamento.objects.filter(
            pk__in=remessa.itens.exclude(equipamento=None).values('equipamento_id')
        )
        equipamentos.update(status='EM_TRANSITO')
        EventoCompra.objects.create(
            remessa=remessa,
            tipo=EventoCompraTipo.REMESSA_ENVIADA,
            usuario=usuario,
        )
        from ordens_servico.models import OrdemServico
        from ordens_servico.services import OrdemServicoService
        ordem = OrdemServicoService.para_remessa_compra(remessa, usuario)
        OrdemServicoService.registrar_transicao(
            ordem, status=OrdemServico.Status.EM_EXECUCAO,
            usuario=usuario, evento='REMESSA_ENVIADA',
        )
        cls._comunicar(
            remessa, usuario, EventoCompraTipo.REMESSA_ENVIADA,
            f'Remessa {remessa.protocolo} aguardando conferência',
            f'A remessa para {remessa.base_destino.nome} está pronta para conferência.',
        )
        return remessa

    @classmethod
    @transaction.atomic
    def confirmar(
        cls, *, remessa, usuario, idempotency_key, linhas, finalizar=False,
        observacao='', item_inesperado=None,
    ):
        remessa = RemessaCompra.objects.select_for_update().get(pk=remessa.pk)
        if not AquisicaoAccessPolicy.pode_confirmar(usuario, remessa):
            raise PermissionDenied('Sem permissão para confirmar esta remessa.')
        existente = RecebimentoRemessa.objects.filter(
            remessa=remessa, idempotency_key=idempotency_key,
        ).first()
        if existente:
            return existente
        if remessa.status not in {
            RemessaCompra.Status.EM_TRANSITO,
            RemessaCompra.Status.AGUARDANDO_CONFERENCIA,
            RemessaCompra.Status.RECEBIDA_PARCIAL,
        }:
            raise ValidationError('A remessa não está disponível para conferência.')
        recebimento = RecebimentoRemessa.objects.create(
            remessa=remessa, idempotency_key=idempotency_key,
            recebido_por=usuario, finaliza_conferencia=finalizar,
            observacao=str(observacao or '').strip(),
        )
        for dados_linha in linhas:
            # Both item targets are nullable and therefore use outer joins.
            # PostgreSQL can only lock the concrete remittance-item row here.
            item = (
                ItemRemessaCompra.objects
                .select_for_update(of=('self',))
                .select_related('insumo', 'equipamento')
                .get(pk=dados_linha['item_id'], remessa=remessa)
            )
            qtd = Decimal(str(dados_linha.get('quantidade_recebida', 0)))
            avaria = Decimal(str(dados_linha.get('quantidade_avariada', 0)))
            falta = Decimal(str(dados_linha.get('quantidade_faltante', 0)))
            if min(qtd, avaria, falta) < 0:
                raise ValidationError('Quantidades de conferência não podem ser negativas.')
            if item.equipamento_id and qtd not in {Decimal('0'), Decimal('1')}:
                raise ValidationError('Equipamento deve ser confirmado individualmente.')
            LinhaRecebimentoRemessa.objects.create(
                recebimento=recebimento, item=item,
                quantidade_recebida=qtd, quantidade_avariada=avaria,
                quantidade_faltante=falta,
                quantidade_esperada_aquisicao=(
                    item.item_aquisicao.quantidade
                    if item.item_aquisicao_id else item.quantidade_prevista
                ),
                quantidade_esperada_nfe=(
                    item.item_nfe.quantidade if item.item_nfe_id else None
                ),
                observacao=str(dados_linha.get('observacao', '')).strip(),
            )
            if avaria > 0:
                DivergenciaRecebimentoCompra.objects.create(
                    recebimento=recebimento,
                    item=item,
                    tipo=DivergenciaRecebimentoCompra.Tipo.AVARIA,
                    quantidade_esperada=Decimal('0'),
                    quantidade_informada=avaria,
                    observacao=str(dados_linha.get('observacao', '')).strip(),
                )
            if falta > 0:
                DivergenciaRecebimentoCompra.objects.create(
                    recebimento=recebimento,
                    item=item,
                    tipo=DivergenciaRecebimentoCompra.Tipo.FALTA,
                    quantidade_esperada=item.quantidade_prevista,
                    quantidade_informada=falta,
                    observacao=str(dados_linha.get('observacao', '')).strip(),
                )
            item.quantidade_recebida += qtd
            item.quantidade_avariada += avaria
            item.quantidade_faltante += falta
            if item.insumo_id and qtd > 0:
                if remessa.fluxo == RemessaCompra.Fluxo.ENTRE_BASES:
                    saldo_origem = SaldoInsumoService.bloquear(remessa.base_origem, item.insumo)
                    if saldo_origem.saldo_reservado < qtd:
                        raise ValidationError('A quantidade recebida excede a reserva da origem.')
                    saldo_origem.saldo_reservado -= qtd
                    saldo_origem.save(update_fields=['saldo_reservado', 'recalculado_em'])
                    MovimentacaoService.saida(
                        base=remessa.base_origem, insumo=item.insumo, quantidade=qtd,
                        usuario=remessa.criada_por,
                        observacao=(
                            f'Remessa {remessa.protocolo}; conferida por '
                            f'{usuario.get_username()}'
                        ),
                    )
                MovimentacaoService.entrada(
                    base=remessa.base_destino, insumo=item.insumo, quantidade=qtd,
                    usuario=usuario, valor_unitario=item.custo_unitario_snapshot,
                    observacao=f'Recebimento da remessa {remessa.protocolo}',
                )
            elif item.equipamento_id and qtd == 1:
                item.equipamento.regional = remessa.base_destino
                item.equipamento.status = 'ATIVO'
                item.equipamento.save(update_fields=['regional', 'status', 'data_atualizacao'])
            item.save(update_fields=[
                'quantidade_recebida', 'quantidade_avariada', 'quantidade_faltante',
            ])

        inesperado = item_inesperado or {}
        descricao_inesperada = str(inesperado.get('descricao', '') or '').strip()
        try:
            quantidade_inesperada = Decimal(str(inesperado.get('quantidade', 0) or 0))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError('A quantidade do item inesperado é inválida.') from exc
        if quantidade_inesperada < 0:
            raise ValidationError('A quantidade do item inesperado não pode ser negativa.')
        if descricao_inesperada or quantidade_inesperada:
            if not descricao_inesperada or quantidade_inesperada <= 0:
                raise ValidationError(
                    'Informe descrição e quantidade positiva para o item inesperado.'
                )
            DivergenciaRecebimentoCompra.objects.create(
                recebimento=recebimento,
                tipo=DivergenciaRecebimentoCompra.Tipo.ITEM_INESPERADO,
                quantidade_esperada=Decimal('0'),
                quantidade_informada=quantidade_inesperada,
                descricao=descricao_inesperada,
                observacao=str(inesperado.get('observacao', '') or '').strip(),
            )

        itens = list(remessa.itens.select_for_update(of=('self',)).select_related(
            'item_aquisicao', 'item_nfe',
        ))
        if finalizar:
            if remessa.fluxo == RemessaCompra.Fluxo.ENTRE_BASES:
                for item in itens:
                    restante = min(
                        item.quantidade_prevista - item.quantidade_recebida,
                        SaldoInsumoBase.objects.get(
                            base=remessa.base_origem, insumo=item.insumo
                        ).saldo_reservado,
                    )
                    if restante > 0:
                        saldo = SaldoInsumoService.bloquear(remessa.base_origem, item.insumo)
                        saldo.saldo_reservado -= restante
                        saldo.save(update_fields=['saldo_reservado', 'recalculado_em'])
            aquisicao_tem_nfe = bool(
                remessa.aquisicao_id
                and hasattr(remessa.aquisicao, 'nota_fiscal')
            )
            for item in itens:
                quantidade_fisica = item.quantidade_recebida + item.quantidade_avariada
                if quantidade_fisica > item.quantidade_prevista:
                    DivergenciaRecebimentoCompra.objects.create(
                        recebimento=recebimento,
                        item=item,
                        tipo=DivergenciaRecebimentoCompra.Tipo.QUANTIDADE_AQUISICAO,
                        quantidade_esperada=item.quantidade_prevista,
                        quantidade_informada=quantidade_fisica,
                    )
                if item.item_nfe_id:
                    total_fisico_nfe = ItemRemessaCompra.objects.filter(
                        item_nfe_id=item.item_nfe_id,
                    ).aggregate(
                        recebida=Sum('quantidade_recebida'),
                        avariada=Sum('quantidade_avariada'),
                    )
                    recebido_nfe = (
                        (total_fisico_nfe['recebida'] or Decimal('0'))
                        + (total_fisico_nfe['avariada'] or Decimal('0'))
                    )
                    if recebido_nfe > item.item_nfe.quantidade:
                        DivergenciaRecebimentoCompra.objects.create(
                            recebimento=recebimento,
                            item=item,
                            tipo=DivergenciaRecebimentoCompra.Tipo.QUANTIDADE_NFE,
                            quantidade_esperada=item.item_nfe.quantidade,
                            quantidade_informada=recebido_nfe,
                        )
                elif aquisicao_tem_nfe:
                    DivergenciaRecebimentoCompra.objects.create(
                        recebimento=recebimento,
                        item=item,
                        tipo=DivergenciaRecebimentoCompra.Tipo.ITEM_SEM_NFE,
                        descricao='Linha da remessa sem correspondência confirmada na NF-e.',
                    )
            # A falta simples mantém a remessa como parcial e permite uma nova
            # entrega. Avaria, excesso, item inesperado ou ausência na NF-e
            # encerram a conferência como divergente.
            tem_divergencia = DivergenciaRecebimentoCompra.objects.filter(
                recebimento__remessa=remessa,
            ).exclude(
                tipo=DivergenciaRecebimentoCompra.Tipo.FALTA,
            ).exists()
            incompleta = any(
                item.quantidade_recebida + item.quantidade_avariada
                != item.quantidade_prevista
                for item in itens
            )
            if tem_divergencia:
                remessa.status = RemessaCompra.Status.RECEBIDA_DIVERGENCIA
            elif incompleta:
                remessa.status = RemessaCompra.Status.RECEBIDA_PARCIAL
            else:
                remessa.status = RemessaCompra.Status.RECEBIDA
        else:
            remessa.status = RemessaCompra.Status.AGUARDANDO_CONFERENCIA
        remessa.save(update_fields=['status', 'atualizada_em'])
        if remessa.aquisicao_id:
            aquisicao = Aquisicao.objects.select_for_update().get(pk=remessa.aquisicao_id)
            itens_aquisicao = list(aquisicao.itens.all())
            completa = bool(itens_aquisicao) and all(
                (
                    ItemRemessaCompra.objects.filter(
                        item_aquisicao=item_aquisicao,
                    ).aggregate(total=Sum('quantidade_recebida'))['total']
                    or Decimal('0')
                ) >= item_aquisicao.quantidade
                for item_aquisicao in itens_aquisicao
            )
            possui_divergencia = DivergenciaRecebimentoCompra.objects.filter(
                recebimento__remessa__aquisicao=aquisicao,
            ).exclude(tipo=DivergenciaRecebimentoCompra.Tipo.FALTA).exists()
            novo_status = (
                Aquisicao.Status.RECEBIDA
                if completa and not possui_divergencia
                else Aquisicao.Status.EM_RECEBIMENTO
            )
            if aquisicao.status != novo_status:
                aquisicao.status = novo_status
                aquisicao.save(update_fields=['status', 'atualizado_em'])
        EventoCompra.objects.create(
            remessa=remessa,
            tipo=EventoCompraTipo.REMESSA_CONFERIDA,
            usuario=usuario,
            dados={
                'recebimento_id': recebimento.pk,
                'finalizada': finalizar,
                'status': remessa.status,
                'divergencias': recebimento.divergencias.count(),
            },
        )
        if finalizar and recebimento.divergencias.exists():
            EventoCompra.objects.create(
                remessa=remessa,
                tipo=EventoCompraTipo.RECEBIMENTO_DIVERGENTE,
                usuario=usuario,
                dados={
                    'recebimento_id': recebimento.pk,
                    'status': remessa.status,
                    'divergencias': recebimento.divergencias.count(),
                },
            )
        from ordens_servico.models import OrdemServico
        from ordens_servico.services import OrdemServicoService
        ordem = OrdemServicoService.para_remessa_compra(remessa, usuario)
        status_os = (
            OrdemServico.Status.CONCLUIDA
            if finalizar else OrdemServico.Status.AGUARDANDO_CONFIRMACAO
        )
        OrdemServicoService.registrar_transicao(
            ordem, status=status_os, usuario=usuario,
            evento='REMESSA_CONFERIDA', dados={'status_remessa': remessa.status},
        )
        cls._comunicar(
            remessa, usuario, EventoCompraTipo.REMESSA_CONFERIDA,
            f'Remessa {remessa.protocolo} conferida',
            f'Conferência registrada por {usuario.get_username()}. Status: {remessa.get_status_display()}.',
        )
        return recebimento


class IndividualizacaoRecebimentoService:
    """Cria a unidade física somente após seu recebimento ter sido confirmado."""

    @classmethod
    def pode_individualizar(cls, *, item_remessa, usuario):
        if not ComprasAccessPolicy.pode_gerenciar_catalogo(usuario):
            return False
        return secure_base_queryset(
            Base.objects.all(),
            usuario,
            action='CRIAR',
        ).filter(pk=item_remessa.remessa.base_destino_id).exists()

    @classmethod
    @transaction.atomic
    def criar_unidade(cls, *, item_remessa, usuario, dados):
        item = (
            ItemRemessaCompra.objects
            .select_for_update()
            .select_related(
                'produto', 'remessa__empresa', 'remessa__base_destino',
                'remessa__aquisicao__fornecedor', 'item_aquisicao',
            )
            .get(pk=item_remessa.pk)
        )
        if not cls.pode_individualizar(item_remessa=item, usuario=usuario):
            raise PermissionDenied('Sem permissão para individualizar itens nesta Base.')
        if not item.produto_id or not item.item_aquisicao_id:
            raise ValidationError(
                'Somente modelos de equipamento vinculados à aquisição podem ser individualizados.'
            )
        if item.quantidade_recebida <= 0:
            raise ValidationError('Nenhuma unidade sem avaria foi recebida para individualização.')
        if item.quantidade_recebida != item.quantidade_recebida.to_integral_value():
            raise ValidationError('Equipamentos individualizados exigem quantidade inteira.')
        if not AtivoCapacidadeService.habilitada(
            empresa=item.remessa.empresa,
            produto=item.produto,
            codigo=CapacidadeCatalogoProdutoEmpresa.INDIVIDUALIZAVEL,
        ):
            raise ValidationError('Este modelo não está habilitado para individualização.')
        if item.equipamentos_individualizados.count() >= int(item.quantidade_recebida):
            raise ValidationError('Todas as unidades recebidas já foram individualizadas.')

        aquisicao = item.item_aquisicao.aquisicao
        equipamento = Equipamento(
            produto=item.produto,
            regional=item.remessa.base_destino,
            numero_serie=dados.get('numero_serie'),
            patrimonio=dados.get('patrimonio'),
            imei_1=dados.get('imei_1'),
            imei_2=dados.get('imei_2'),
            finalidade=dados.get('finalidade') or Equipamento.Finalidade.OPERACIONAL,
            responsavel=str(dados.get('responsavel') or '').strip(),
            observacao_operacional=str(
                dados.get('observacao_operacional') or ''
            ).strip(),
            foto=dados.get('foto'),
            status='ATIVO',
            data_aquisicao=aquisicao.data_compra,
            fornecedor=aquisicao.fornecedor,
            custo_aquisicao=item.item_aquisicao.valor_unitario,
            origem_valor=Equipamento.OrigemValor.DOCUMENTO_COMPRA,
            documento_compra=aquisicao.numero_documento,
        )
        equipamento.save()

        vinculo = VinculoEquipamentoAquisicao(
            item=item.item_aquisicao,
            item_remessa=item,
            equipamento=equipamento,
            valor_aquisicao_snapshot=item.item_aquisicao.valor_unitario,
        )
        vinculo.full_clean()
        vinculo.save()
        HistoricoValorEquipamento.objects.create(
            equipamento=equipamento,
            custo_anterior=None,
            custo_novo=item.item_aquisicao.valor_unitario,
            referencia_anterior=None,
            referencia_nova=equipamento.preco_referencia,
            origem_anterior='',
            origem_nova=Equipamento.OrigemValor.DOCUMENTO_COMPRA,
            motivo=f'Individualização do recebimento {item.remessa.protocolo}',
            alterado_por=usuario,
        )
        Historico.objects.create(
            equipamento=equipamento,
            tipo_acao='CRIACAO',
            usuario=usuario,
            detalhes={
                'mensagem': 'Equipamento individualizado após recebimento',
                'remessa_id': item.remessa_id,
                'item_remessa_id': item.pk,
                'numero_serie': equipamento.numero_serie,
                'patrimonio': equipamento.patrimonio,
                'imei_1': equipamento.imei_1,
                'imei_2': equipamento.imei_2,
            },
        )
        EventoCompra.objects.create(
            remessa=item.remessa,
            tipo=EventoCompraTipo.EQUIPAMENTO_INDIVIDUALIZADO,
            usuario=usuario,
            dados={
                'item_remessa_id': item.pk,
                'equipamento_id': equipamento.pk,
                'pendentes': str(item.quantidade_pendente_individualizacao),
            },
        )
        return equipamento
