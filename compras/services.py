from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from compras.models import (
    Aquisicao,
    EventoCompra,
    HistoricoValorEquipamento,
    ItemAquisicao,
    ItemRemessaCompra,
    LinhaRecebimentoRemessa,
    RecebimentoRemessa,
    RemessaCompra,
    VinculoEquipamentoAquisicao,
)
from compras.policies import AquisicaoAccessPolicy
from estoque.models import Equipamento
from estoque.policies.compras import ComprasAccessPolicy
from estoque.services.comunicado_service import ComunicadoService
from insumos.models import SaldoInsumoBase
from insumos.services.movimentacao_service import MovimentacaoService
from insumos.services.saldo_service import SaldoInsumoService


class AquisicaoService:
    @classmethod
    @transaction.atomic
    def criar(cls, *, empresa, fornecedor, usuario, itens, **dados):
        if not AquisicaoAccessPolicy.pode_gerenciar(usuario):
            raise PermissionDenied('Sem permissão para gerenciar aquisições.')
        if not itens:
            raise ValidationError('Inclua ao menos um item na aquisição.')
        if not ComprasAccessPolicy.empresas(usuario).filter(pk=empresa.pk).exists():
            raise PermissionDenied('Empresa fora do escopo corporativo de Compras.')
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
            aquisicao=aquisicao, tipo='AQUISICAO_CRIADA', usuario=usuario,
            dados={'itens': len(itens)},
        )
        transaction.on_commit(lambda: ComunicadoService.criar_acao(
            titulo=f'Aquisicao #{aquisicao.pk} criada',
            mensagem=(
                f'Aquisicao registrada para {empresa.nome}, fornecedor '
                f'{fornecedor.nome}, com {len(itens)} item(ns).'
            ),
            usuario=usuario,
            empresa=empresa,
            dados={'aquisicao_id': aquisicao.pk, 'acao': 'CRIADA'},
            url=f'/compras/{aquisicao.pk}/',
        ))
        return aquisicao

    @classmethod
    @transaction.atomic
    def aprovar(cls, aquisicao, usuario):
        if not AquisicaoAccessPolicy.pode_gerenciar(usuario):
            raise PermissionDenied('Sem permissão para aprovar a aquisição.')
        aquisicao = Aquisicao.objects.select_for_update().get(pk=aquisicao.pk)
        if aquisicao.status != Aquisicao.Status.RASCUNHO:
            raise ValidationError('Somente aquisições em rascunho podem ser aprovadas.')
        aquisicao.status = Aquisicao.Status.APROVADA
        aquisicao.aprovado_por = usuario
        aquisicao.aprovado_em = timezone.now()
        aquisicao.save(update_fields=['status', 'aprovado_por', 'aprovado_em', 'atualizado_em'])
        EventoCompra.objects.create(
            aquisicao=aquisicao, tipo='AQUISICAO_APROVADA', usuario=usuario,
        )
        transaction.on_commit(lambda: ComunicadoService.criar_acao(
            titulo=f'Aquisicao #{aquisicao.pk} aprovada',
            mensagem=f'A aquisicao de {aquisicao.fornecedor.nome} foi aprovada.',
            usuario=usuario,
            usuarios=[aquisicao.cadastrado_por],
            empresa=aquisicao.empresa,
            dados={'aquisicao_id': aquisicao.pk, 'acao': 'APROVADA'},
            url=f'/compras/{aquisicao.pk}/',
        ))
        return aquisicao

    @classmethod
    @transaction.atomic
    def vincular_equipamento(cls, *, item, equipamento, usuario):
        if not AquisicaoAccessPolicy.pode_gerenciar(usuario):
            raise PermissionDenied('Sem permissão para vincular equipamentos.')
        item = ItemAquisicao.objects.select_for_update().select_related('aquisicao').get(pk=item.pk)
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
        transaction.on_commit(lambda: ComunicadoService.criar_acao(
            titulo=f'Valor do equipamento {equipamento.codigo} atualizado',
            mensagem=f'O valor patrimonial foi atualizado. Motivo: {motivo}',
            usuario=usuario,
            bases=[equipamento.regional],
            empresa=equipamento.regional.empresa,
            dados={'equipamento_id': equipamento.pk, 'acao': 'VALOR_ATUALIZADO'},
            url='/compras/valores/equipamentos/',
        ))
        return equipamento

    @staticmethod
    @transaction.atomic
    def atualizar_valores_equipamentos_em_lote(*, itens, usuario):
        if not ComprasAccessPolicy.pode_editar_precos(usuario):
            raise PermissionDenied('Sem permissão para editar valores de equipamentos.')
        if not itens:
            return 0, 0

        ids = [item['equipamento_id'] for item in itens]
        equipamentos = {
            equipamento.pk: equipamento
            for equipamento in Equipamento.objects.select_for_update().select_related(
                'regional__empresa'
            ).filter(pk__in=ids)
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
    def _comunicar(remessa, usuario, titulo, mensagem):
        transaction.on_commit(lambda: ComunicadoService.criar_acao(
            titulo=titulo,
            mensagem=mensagem,
            usuario=usuario,
            bases=[remessa.base_destino],
            empresa=remessa.empresa,
            incluir_admins=True,
            dados={'remessa_id': remessa.pk, 'protocolo': remessa.protocolo},
        ))

    @classmethod
    @transaction.atomic
    def criar(cls, *, empresa, fluxo, base_destino, usuario, itens, aquisicao=None, base_origem=None, **dados):
        if not ComprasAccessPolicy.pode_criar_remessa(usuario):
            raise PermissionDenied('Sem permissão para criar remessas.')
        if not itens:
            raise ValidationError('Inclua ao menos um item na remessa.')
        if not ComprasAccessPolicy.bases(usuario).filter(pk=base_destino.pk).exists():
            raise PermissionDenied('Base de destino fora do escopo de Compras.')
        remessa = RemessaCompra(
            empresa=empresa, fluxo=fluxo, base_destino=base_destino,
            base_origem=base_origem, aquisicao=aquisicao, criada_por=usuario, **dados,
        )
        remessa.full_clean()
        remessa.save()
        for dados_item in itens:
            item = ItemRemessaCompra(remessa=remessa, **dados_item)
            item.full_clean()
            if fluxo == RemessaCompra.Fluxo.ENTRE_BASES:
                if item.equipamento_id:
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
            remessa=remessa, tipo='REMESSA_CRIADA', usuario=usuario,
            dados={'fluxo': fluxo, 'itens': len(itens)},
        )
        cls._comunicar(
            remessa, usuario, f'Remessa {remessa.protocolo} criada',
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
        EventoCompra.objects.create(remessa=remessa, tipo='REMESSA_ENVIADA', usuario=usuario)
        from ordens_servico.models import OrdemServico
        from ordens_servico.services import OrdemServicoService
        ordem = OrdemServicoService.para_remessa_compra(remessa, usuario)
        OrdemServicoService.registrar_transicao(
            ordem, status=OrdemServico.Status.EM_EXECUCAO,
            usuario=usuario, evento='REMESSA_ENVIADA',
        )
        cls._comunicar(
            remessa, usuario, f'Remessa {remessa.protocolo} aguardando conferência',
            f'A remessa para {remessa.base_destino.nome} está pronta para conferência.',
        )
        return remessa

    @classmethod
    @transaction.atomic
    def confirmar(cls, *, remessa, usuario, idempotency_key, linhas, finalizar=False, observacao=''):
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
            item = ItemRemessaCompra.objects.select_for_update().select_related(
                'insumo', 'equipamento'
            ).get(pk=dados_linha['item_id'], remessa=remessa)
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
                        usuario=usuario, observacao=f'Remessa {remessa.protocolo}',
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

        itens = list(remessa.itens.select_for_update())
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
            tem_avaria = any(item.quantidade_avariada > 0 for item in itens)
            incompleta = any(item.quantidade_recebida != item.quantidade_prevista for item in itens)
            if tem_avaria:
                remessa.status = RemessaCompra.Status.RECEBIDA_DIVERGENCIA
            elif incompleta:
                remessa.status = RemessaCompra.Status.RECEBIDA_PARCIAL
            else:
                remessa.status = RemessaCompra.Status.RECEBIDA
        else:
            remessa.status = RemessaCompra.Status.AGUARDANDO_CONFERENCIA
        remessa.save(update_fields=['status', 'atualizada_em'])
        EventoCompra.objects.create(
            remessa=remessa, tipo='REMESSA_CONFERIDA', usuario=usuario,
            dados={'recebimento_id': recebimento.pk, 'finalizada': finalizar, 'status': remessa.status},
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
            remessa, usuario, f'Remessa {remessa.protocolo} conferida',
            f'Conferência registrada por {usuario.get_username()}. Status: {remessa.get_status_display()}.',
        )
        return recebimento
