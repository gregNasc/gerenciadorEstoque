import hashlib
import json
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from estoque.models import Empresa
from ordens_servico.models import (
    OrdemServico,
    OrdemServicoAssinatura,
    OrdemServicoEvento,
    OrdemServicoLinha,
    SequenciaOrdemServico,
)
from ordens_servico.policies import OrdemServicoAccessPolicy


class OrdemServicoService:
    @classmethod
    def _proximo_numero(cls, empresa):
        ano = timezone.localdate().year
        Empresa.objects.select_for_update().get(pk=empresa.pk)
        sequencia, _ = SequenciaOrdemServico.objects.select_for_update().get_or_create(
            empresa=empresa,
            ano=ano,
            defaults={'ultimo_numero': 0},
        )
        sequencia.ultimo_numero += 1
        sequencia.save(update_fields=['ultimo_numero'])
        return ano, f'OS-{ano}-{sequencia.ultimo_numero:06d}'

    @classmethod
    @transaction.atomic
    def criar(cls, *, empresa, tipo, solicitante, motivo, status=None, prioridade=None, **campos):
        ano, numero = cls._proximo_numero(empresa)
        ordem = OrdemServico(
            numero=numero,
            ano=ano,
            empresa=empresa,
            tipo=tipo,
            solicitante=solicitante,
            motivo=str(motivo or '').strip() or tipo,
            status=status or OrdemServico.Status.AGUARDANDO_AUTORIZACAO,
            prioridade=prioridade or OrdemServico.Prioridade.NORMAL,
            **campos,
        )
        ordem.full_clean()
        ordem.save()
        OrdemServicoEvento.objects.create(
            ordem=ordem,
            tipo='OS_CRIADA',
            usuario=solicitante,
            dados={'status': ordem.status, 'tipo': ordem.tipo},
        )
        return ordem

    @staticmethod
    def _linha_equipamento(ordem, equipamento, *, natureza=OrdemServicoLinha.Natureza.EQUIPAMENTO):
        produto = equipamento.produto
        return OrdemServicoLinha.objects.create(
            ordem=ordem,
            natureza=natureza,
            equipamento=equipamento,
            descricao=produto.descricao if produto else str(equipamento),
            fabricante=produto.fabricante if produto else '',
            modelo=produto.modelo if produto else '',
            codigo=equipamento.codigo,
            patrimonio=equipamento.patrimonio,
            numero_serie=equipamento.numero_serie,
            origem=equipamento.regional.nome,
            condicao_saida=equipamento.get_status_display(),
            dados_snapshot={
                'equipamento_id': equipamento.pk,
                'produto_id': equipamento.produto_id,
                'status': equipamento.status,
                'finalidade': equipamento.finalidade,
            },
        )

    @classmethod
    @transaction.atomic
    def para_transferencia(cls, transferencia, usuario):
        ordem = OrdemServico.objects.filter(transferencia=transferencia).first()
        if ordem:
            return ordem
        ordem = cls.criar(
            empresa=transferencia.regional_origem.empresa,
            tipo=OrdemServico.Tipo.TRANSFERENCIA,
            solicitante=usuario,
            motivo=f'Transferência {transferencia.protocolo}',
            base_responsavel=transferencia.regional_origem,
            base_origem=transferencia.regional_origem,
            base_destino=transferencia.regional_destino,
            transferencia=transferencia,
        )
        for item in transferencia.itens.select_related('equipamento__produto', 'equipamento__regional'):
            linha = cls._linha_equipamento(ordem, item.equipamento)
            linha.destino = transferencia.regional_destino.nome
            linha.save(update_fields=['destino'])
        return ordem

    @classmethod
    @transaction.atomic
    def para_emprestimo(cls, emprestimo, usuario):
        ordem = OrdemServico.objects.filter(emprestimo=emprestimo).first()
        if not ordem:
            from datetime import datetime, time
            ordem = cls.criar(
                empresa=emprestimo.regional_origem.empresa,
                tipo=OrdemServico.Tipo.EMPRESTIMO,
                solicitante=usuario,
                motivo=emprestimo.motivo,
                descricao=f'Empréstimo {emprestimo.protocolo}',
                prazo_em=timezone.make_aware(
                    datetime.combine(emprestimo.data_prevista_devolucao, time.max)
                ),
                base_responsavel=emprestimo.regional_origem,
                base_origem=emprestimo.regional_origem,
                base_destino=emprestimo.regional_destino,
                emprestimo=emprestimo,
            )
        existentes = set(ordem.linhas.values_list('equipamento_id', flat=True))
        for item in emprestimo.itens.select_related('equipamento__produto', 'equipamento__regional'):
            if item.equipamento_id in existentes:
                continue
            linha = cls._linha_equipamento(ordem, item.equipamento)
            linha.destino = emprestimo.regional_destino.nome
            linha.save(update_fields=['destino'])
        return ordem

    @classmethod
    @transaction.atomic
    def para_sick(cls, sick, usuario):
        ordem = OrdemServico.objects.filter(sick=sick).first()
        if ordem:
            return ordem
        ordem = cls.criar(
            empresa=sick.equipamento.regional.empresa,
            tipo=OrdemServico.Tipo.SICK,
            solicitante=usuario,
            motivo=sick.motivo,
            descricao=sick.descricao,
            status=OrdemServico.Status.EM_EXECUCAO,
            base_responsavel=sick.base_origem or sick.equipamento.regional,
            base_origem=sick.base_origem or sick.equipamento.regional,
            sick=sick,
            executado_em=timezone.now(),
        )
        cls._linha_equipamento(ordem, sick.equipamento)
        return ordem

    @classmethod
    @transaction.atomic
    def para_movimentacao_insumo(cls, movimentacao, usuario):
        ordem = OrdemServico.objects.filter(movimentacao_insumo=movimentacao).first()
        if ordem:
            return ordem
        tipo = (
            OrdemServico.Tipo.CONSUMO
            if movimentacao.tipo in {'SAIDA', 'PERDA'} else OrdemServico.Tipo.INSUMO
        )
        ordem = cls.criar(
            empresa=movimentacao.base.empresa,
            tipo=tipo,
            solicitante=usuario,
            motivo=movimentacao.observacao or movimentacao.get_tipo_display(),
            status=OrdemServico.Status.CONCLUIDA,
            base_responsavel=movimentacao.base,
            base_origem=movimentacao.base,
            movimentacao_insumo=movimentacao,
            executado_em=movimentacao.criado_em,
            confirmado_em=movimentacao.criado_em,
            encerrado_em=movimentacao.criado_em,
        )
        natureza = (
            OrdemServicoLinha.Natureza.INSUMO_CONSUMIDO
            if movimentacao.tipo in {'SAIDA', 'PERDA', 'AJUSTE_SAIDA'}
            else OrdemServicoLinha.Natureza.INSUMO_TRANSFERIDO
        )
        OrdemServicoLinha.objects.create(
            ordem=ordem,
            natureza=natureza,
            insumo=movimentacao.insumo,
            descricao=movimentacao.insumo.descricao,
            unidade=movimentacao.insumo.unidade_medida,
            quantidade=movimentacao.quantidade,
            origem=movimentacao.base.nome,
            custo_unitario_historico=movimentacao.valor_unitario,
            dados_snapshot={
                'movimentacao_id': movimentacao.pk,
                'tipo': movimentacao.tipo,
                'insumo_id': movimentacao.insumo_id,
            },
        )
        return ordem

    @classmethod
    @transaction.atomic
    def para_solicitacao_insumo(cls, solicitacao, usuario):
        ordem = OrdemServico.objects.filter(solicitacao_insumo=solicitacao).first()
        if not ordem:
            prioridade = (
                OrdemServico.Prioridade.URGENTE
                if solicitacao.prioridade in {'ALTA', 'URGENTE'}
                else OrdemServico.Prioridade.NORMAL
            )
            ordem = cls.criar(
                empresa=solicitacao.base.empresa,
                tipo=OrdemServico.Tipo.INSUMO,
                solicitante=solicitacao.solicitante,
                motivo=f'Encaminhamento de insumos {solicitacao.protocolo}',
                descricao=solicitacao.justificativa,
                prioridade=prioridade,
                justificativa_urgencia=(
                    solicitacao.justificativa or 'Prioridade definida na solicitação.'
                    if prioridade != OrdemServico.Prioridade.NORMAL else ''
                ),
                status=OrdemServico.Status.EM_EXECUCAO,
                base_responsavel=solicitacao.base,
                base_destino=solicitacao.base,
                solicitacao_insumo=solicitacao,
                responsavel_operacional=usuario,
                executado_em=timezone.now(),
            )
        existentes = set(ordem.linhas.values_list('insumo_id', flat=True))
        for item in solicitacao.itens.select_related('insumo'):
            if item.insumo_id in existentes:
                continue
            OrdemServicoLinha.objects.create(
                ordem=ordem,
                natureza=OrdemServicoLinha.Natureza.INSUMO_TRANSFERIDO,
                insumo=item.insumo,
                descricao=item.insumo.descricao,
                unidade=item.insumo.unidade_medida,
                quantidade=item.quantidade,
                destino=solicitacao.base.nome,
                dados_snapshot={
                    'solicitacao_id': solicitacao.pk,
                    'item_solicitacao_id': item.pk,
                    'insumo_id': item.insumo_id,
                    'observacao': item.observacao,
                },
            )
        return ordem

    @classmethod
    def hash_documento(cls, ordem):
        payload = {
            'numero': ordem.numero,
            'tipo': ordem.tipo,
            'status': ordem.status,
            'empresa_id': ordem.empresa_id,
            'origem_id': ordem.base_origem_id,
            'destino_id': ordem.base_destino_id,
            'motivo': ordem.motivo,
            'linhas': list(ordem.linhas.order_by('pk').values(
                'natureza', 'descricao', 'codigo', 'quantidade', 'patrimonio',
                'numero_serie', 'origem', 'destino', 'custo_unitario_historico',
            )),
        }
        texto = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(texto.encode('utf-8')).hexdigest()

    @classmethod
    @transaction.atomic
    def assinar(cls, *, ordem, usuario, senha, tipo, ip=None, user_agent=''):
        ordem = OrdemServico.objects.select_for_update().get(pk=ordem.pk)
        if not OrdemServicoAccessPolicy.pode_visualizar(usuario, ordem):
            raise PermissionDenied('Sem acesso a esta O.S.')
        if tipo == OrdemServicoAssinatura.Tipo.AUTORIZACAO and not OrdemServicoAccessPolicy.pode_autorizar(usuario):
            raise PermissionDenied('Sem permissão para autorizar esta O.S.')
        if not isinstance(senha, str) or not usuario.check_password(senha):
            raise ValidationError('Senha inválida. A O.S. não foi assinada.')
        if tipo not in OrdemServicoAssinatura.Tipo.values:
            raise ValidationError('Tipo de assinatura inválido.')
        if OrdemServicoAssinatura.objects.filter(ordem=ordem, tipo=tipo).exists():
            raise ValidationError('Esta etapa da O.S. já foi assinada.')
        assinatura = OrdemServicoAssinatura.objects.create(
            ordem=ordem,
            tipo=tipo,
            usuario=usuario,
            hash_documento=cls.hash_documento(ordem),
            ip=ip,
            user_agent=str(user_agent or '')[:255],
        )
        agora = assinatura.assinado_em
        campos = []
        if tipo == OrdemServicoAssinatura.Tipo.AUTORIZACAO:
            ordem.autorizador = usuario
            ordem.autorizado_em = agora
            if ordem.status == OrdemServico.Status.AGUARDANDO_AUTORIZACAO:
                ordem.status = OrdemServico.Status.AUTORIZADA
            campos += ['autorizador', 'autorizado_em', 'status']
        elif tipo == OrdemServicoAssinatura.Tipo.EXECUCAO:
            ordem.responsavel_operacional = usuario
            ordem.executado_em = agora
            campos += ['responsavel_operacional', 'executado_em']
        elif tipo == OrdemServicoAssinatura.Tipo.RECEBIMENTO:
            ordem.recebedor = usuario
            ordem.confirmado_em = agora
            campos += ['recebedor', 'confirmado_em']
        else:
            ordem.encerrado_em = agora
            campos += ['encerrado_em']
        ordem.save(update_fields=list(dict.fromkeys(campos)))
        OrdemServicoEvento.objects.create(
            ordem=ordem,
            tipo=f'OS_ASSINADA_{tipo}',
            usuario=usuario,
            dados={'assinatura_id': assinatura.pk, 'hash_documento': assinatura.hash_documento},
        )
        return assinatura

    @classmethod
    @transaction.atomic
    def registrar_transicao(cls, ordem, *, status, usuario, evento, dados=None):
        ordem = OrdemServico.objects.select_for_update().get(pk=ordem.pk)
        anterior = ordem.status
        ordem.status = status
        agora = timezone.now()
        campos = ['status']
        if status == OrdemServico.Status.EM_EXECUCAO and not ordem.executado_em:
            ordem.executado_em = agora
            campos.append('executado_em')
        elif status == OrdemServico.Status.AGUARDANDO_CONFIRMACAO:
            ordem.confirmado_em = None
            campos.append('confirmado_em')
        elif status == OrdemServico.Status.CONCLUIDA:
            ordem.confirmado_em = ordem.confirmado_em or agora
            ordem.encerrado_em = agora
            campos += ['confirmado_em', 'encerrado_em']
        ordem.save(update_fields=campos)
        OrdemServicoEvento.objects.create(
            ordem=ordem,
            tipo=evento,
            usuario=usuario,
            dados={'status_anterior': anterior, 'status_novo': status, **(dados or {})},
        )
        return ordem
