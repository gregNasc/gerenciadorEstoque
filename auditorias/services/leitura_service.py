from dataclasses import dataclass
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from estoque.models import Emprestimo, Equipamento, TransferenciaItem

from auditorias.models import AuditoriaBase, AuditoriaDivergencia, AuditoriaEvento, AuditoriaLeitura
from auditorias.permissions import exigir_acesso_base


@dataclass(frozen=True)
class ResultadoLeitura:
    leitura: AuditoriaLeitura
    classificacao_resposta: str | None = None

    def to_dict(self):
        leitura = self.leitura
        equipamento = leitura.equipamento
        classificacao = self.classificacao_resposta or leitura.classificacao
        outra_base = classificacao == AuditoriaLeitura.Classificacao.OUTRA_BASE
        dados = {
            'ok': True,
            'leitura_id': leitura.pk,
            'classificacao': classificacao,
            'titulo': 'Divergência identificada' if outra_base else leitura.get_classificacao_display(),
            'mensagem': leitura.dados_classificacao.get('mensagem', ''),
            'equipamento': None,
        }
        if equipamento:
            dados['equipamento'] = {
                'id': equipamento.pk,
                'codigo': equipamento.codigo,
                'produto': equipamento.produto.descricao if equipamento.produto else '',
                'patrimonio': equipamento.patrimonio,
                'numero_serie': equipamento.numero_serie,
                'base_cadastrada': equipamento.regional.nome,
                'base_encontrada': leitura.base_encontrada.nome,
            }
        return dados


class LeituraService:
    STATUS_INCOMPATIVEIS = {'BAIXA', 'INATIVO', 'SUCATA'}

    @staticmethod
    def normalizar(valor):
        return str(valor or '').strip().upper()

    @classmethod
    @transaction.atomic
    def registrar(
        cls,
        *,
        auditoria_base,
        valor,
        usuario,
        origem=AuditoriaLeitura.Origem.MANUAL,
        idempotency_key=None,
    ):
        auditoria = AuditoriaBase.objects.select_for_update().select_related('base', 'campanha').get(
            pk=auditoria_base.pk
        )
        exigir_acesso_base(usuario, auditoria.base)
        agora = timezone.now()
        if auditoria.status not in (AuditoriaBase.Status.EM_ANDAMENTO, AuditoriaBase.Status.REABERTA):
            raise ValidationError('A auditoria não está aberta para coleta.')
        if auditoria.status != AuditoriaBase.Status.REABERTA and not (
            auditoria.inicio_em <= agora <= auditoria.fim_em
        ):
            raise ValidationError('A auditoria está fora da janela de coleta.')

        if idempotency_key:
            try:
                chave = uuid.UUID(str(idempotency_key))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValidationError('Idempotency key inválida.') from exc
            existente = AuditoriaLeitura.objects.filter(idempotency_key=chave).first()
            if existente:
                if existente.auditoria_base_id != auditoria.pk:
                    raise ValidationError('Idempotency key já utilizada em outra auditoria.')
                return ResultadoLeitura(existente)
        else:
            chave = uuid.uuid4()

        normalizado = cls.normalizar(valor)
        if not normalizado:
            raise ValidationError('Informe um patrimônio, número de série ou código.')

        correspondencias = list(
            Equipamento.objects.filter(
                Q(patrimonio__iexact=normalizado)
                | Q(numero_serie__iexact=normalizado)
                | Q(codigo__iexact=normalizado),
                regional__empresa=auditoria.campanha.empresa,
            ).select_related('produto', 'regional').distinct()[:3]
        )

        equipamento = correspondencias[0] if len(correspondencias) == 1 else None
        tipo_identificador = AuditoriaLeitura.Identificador.DESCONHECIDO
        classificacao = AuditoriaLeitura.Classificacao.NAO_CADASTRADO
        mensagem = 'Nenhum equipamento cadastrado foi encontrado para o identificador.'

        if len(correspondencias) > 1:
            classificacao = AuditoriaLeitura.Classificacao.IDENTIFICADOR_DUPLICADO
            mensagem = 'O identificador corresponde a mais de um equipamento.'
        elif equipamento:
            if equipamento.patrimonio.upper() == normalizado:
                tipo_identificador = AuditoriaLeitura.Identificador.PATRIMONIO
            elif equipamento.numero_serie.upper() == normalizado:
                tipo_identificador = AuditoriaLeitura.Identificador.SERIE
            else:
                tipo_identificador = AuditoriaLeitura.Identificador.CODIGO

            anterior = AuditoriaLeitura.objects.filter(
                auditoria_base=auditoria,
                equipamento=equipamento,
                cancelada=False,
            ).first()
            if anterior:
                return ResultadoLeitura(
                    anterior,
                    classificacao_resposta=AuditoriaLeitura.Classificacao.LEITURA_DUPLICADA,
                )

            em_transferencia = TransferenciaItem.objects.filter(
                equipamento=equipamento,
                transferencia__status__in=['PENDENTE', 'EM_TRANSITO'],
            ).exists()
            emprestado = Emprestimo.objects.filter(
                itens__equipamento=equipamento,
            ).exclude(status__in=['FINALIZADO', 'CANCELADO']).exists()
            if em_transferencia:
                classificacao = AuditoriaLeitura.Classificacao.EM_TRANSFERENCIA
                mensagem = 'O equipamento possui uma transferência aberta.'
            elif emprestado:
                classificacao = AuditoriaLeitura.Classificacao.EMPRESTADO
                mensagem = 'O equipamento está vinculado a um empréstimo vigente.'
            elif equipamento.status in cls.STATUS_INCOMPATIVEIS:
                classificacao = AuditoriaLeitura.Classificacao.STATUS_INCOMPATIVEL
                mensagem = f'O equipamento está com status {equipamento.status}.'
            elif equipamento.regional_id == auditoria.base_id:
                classificacao = AuditoriaLeitura.Classificacao.CORRETO
                mensagem = 'Equipamento localizado na base esperada.'
            else:
                classificacao = AuditoriaLeitura.Classificacao.OUTRA_BASE
                mensagem = (
                    f'O equipamento pertence à base {equipamento.regional.nome} '
                    f'e foi encontrado na base {auditoria.base.nome}.'
                )

        leitura = AuditoriaLeitura.objects.create(
            auditoria_base=auditoria,
            equipamento=equipamento,
            valor_informado=str(valor).strip(),
            valor_normalizado=normalizado,
            tipo_identificador=tipo_identificador,
            origem=origem,
            classificacao=classificacao,
            base_encontrada=auditoria.base,
            lida_por=usuario,
            idempotency_key=chave,
            dados_classificacao={'mensagem': mensagem},
        )

        snapshot = None
        if equipamento:
            snapshot = auditoria.snapshot_equipamentos.filter(equipamento=equipamento).first()
        if snapshot:
            divergencias_canceladas = AuditoriaDivergencia.objects.filter(
                auditoria_base=auditoria,
                snapshot=snapshot,
                tipo=AuditoriaDivergencia.Tipo.NAO_LOCALIZADO,
                status__in=[
                    AuditoriaDivergencia.Status.ABERTA,
                    AuditoriaDivergencia.Status.EM_ANALISE,
                ],
            ).update(
                status=AuditoriaDivergencia.Status.CANCELADA,
                resolvida_em=agora,
            )
            if divergencias_canceladas:
                AuditoriaEvento.objects.create(
                    auditoria_base=auditoria,
                    tipo='NAO_LOCALIZADO_CANCELADO_APOS_LEITURA',
                    usuario=usuario,
                    dados={'equipamento_id': equipamento.pk, 'snapshot_id': snapshot.pk},
                )

        mapa_divergencia = {
            AuditoriaLeitura.Classificacao.OUTRA_BASE: AuditoriaDivergencia.Tipo.OUTRA_BASE,
            AuditoriaLeitura.Classificacao.NAO_CADASTRADO: AuditoriaDivergencia.Tipo.NAO_CADASTRADO,
            AuditoriaLeitura.Classificacao.IDENTIFICADOR_DUPLICADO: AuditoriaDivergencia.Tipo.IDENTIFICADOR_DUPLICADO,
            AuditoriaLeitura.Classificacao.STATUS_INCOMPATIVEL: AuditoriaDivergencia.Tipo.STATUS_INCOMPATIVEL,
            AuditoriaLeitura.Classificacao.EM_TRANSFERENCIA: AuditoriaDivergencia.Tipo.CONFLITO_TRANSFERENCIA,
            AuditoriaLeitura.Classificacao.EMPRESTADO: AuditoriaDivergencia.Tipo.CONFLITO_EMPRESTIMO,
        }
        tipo_divergencia = mapa_divergencia.get(classificacao)
        if tipo_divergencia:
            descricao_divergencia = mensagem
            if tipo_divergencia in (
                AuditoriaDivergencia.Tipo.NAO_CADASTRADO,
                AuditoriaDivergencia.Tipo.IDENTIFICADOR_DUPLICADO,
            ):
                descricao_divergencia = (
                    f'{mensagem} Identificador informado: {leitura.valor_informado}.'
                )
            AuditoriaDivergencia.objects.create(
                auditoria_base=auditoria,
                leitura=leitura,
                equipamento=equipamento,
                tipo=tipo_divergencia,
                base_esperada=equipamento.regional if equipamento else None,
                base_encontrada=auditoria.base,
                descricao=descricao_divergencia,
            )

        AuditoriaEvento.objects.create(
            auditoria_base=auditoria,
            tipo='LEITURA_REGISTRADA',
            usuario=usuario,
            dados={
                'leitura_id': leitura.pk,
                'equipamento_id': equipamento.pk if equipamento else None,
                'classificacao': classificacao,
            },
        )
        return ResultadoLeitura(leitura)
