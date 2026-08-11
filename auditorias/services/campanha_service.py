from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from auditorias.models import (
    AuditoriaBase,
    AuditoriaEvento,
    CampanhaAuditoria,
    CampanhaAuditoriaEvento,
)
from auditorias.permissions import exigir_admin


class CampanhaService:
    @staticmethod
    def _evento(campanha, tipo, usuario, dados=None):
        return CampanhaAuditoriaEvento.objects.create(
            campanha=campanha,
            tipo=tipo,
            usuario=usuario,
            dados=dados or {},
        )

    @staticmethod
    def _comunicar(campanha, usuario, titulo, mensagem, bases=None, tipo='OPERACIONAL'):
        def enviar():
            from estoque.services.comunicado_service import ComunicadoService

            ComunicadoService.criar_acao(
                titulo=titulo,
                mensagem=mensagem,
                usuario=usuario,
                usuarios=[campanha.criado_por],
                bases=bases,
                empresa=campanha.empresa,
                tipo=tipo,
                dados={
                    'template_codigo': 'auditoria_campanha_acao',
                    'campanha_id': campanha.pk,
                },
                url=f'/auditorias/{campanha.pk}/',
            )

        transaction.on_commit(enviar)

    @classmethod
    @transaction.atomic
    def criar_campanha(cls, *, empresa, nome, criado_por, descricao='', instrucoes=''):
        exigir_admin(criado_por)
        campanha = CampanhaAuditoria.objects.create(
            empresa=empresa,
            nome=nome,
            descricao=descricao,
            instrucoes=instrucoes,
            criado_por=criado_por,
        )
        cls._evento(campanha, 'CAMPANHA_CRIADA', criado_por)
        cls._comunicar(
            campanha,
            criado_por,
            f'CAMPANHA DE AUDITORIA CRIADA: {campanha.nome}',
            f'A CAMPANHA {campanha.nome} FOI CRIADA PARA {campanha.empresa.nome}.',
        )
        return campanha

    @classmethod
    @transaction.atomic
    def editar_campanha(cls, campanha, *, usuario, justificativa='', **dados):
        exigir_admin(usuario)
        campanha = CampanhaAuditoria.objects.select_for_update().get(pk=campanha.pk)
        if campanha.status in {
            CampanhaAuditoria.Status.ENCERRADA,
            CampanhaAuditoria.Status.CANCELADA,
        }:
            raise ValidationError('CAMPANHA ENCERRADA OU CANCELADA NÃO PODE SER EDITADA.')

        dados = dados.copy()
        for campo in ('nome', 'descricao', 'instrucoes'):
            if campo in dados and isinstance(dados[campo], str):
                dados[campo] = dados[campo].upper()
        alterados = [campo for campo, valor in dados.items() if getattr(campanha, campo) != valor]
        if not alterados:
            return campanha
        if 'empresa' in alterados and campanha.auditorias_bases.exists():
            raise ValidationError('A EMPRESA SÓ PODE MUDAR SEM BASES PARTICIPANTES.')
        if campanha.status != CampanhaAuditoria.Status.RASCUNHO and not justificativa.strip():
            raise ValidationError('ALTERAÇÕES APÓS O RASCUNHO EXIGEM JUSTIFICATIVA.')

        anteriores = {campo: str(getattr(campanha, campo)) for campo in alterados}
        for campo, valor in dados.items():
            setattr(campanha, campo, valor)
        campanha.full_clean()
        campanha.save(update_fields=[*alterados, 'atualizado_em'])
        cls._evento(
            campanha,
            'CAMPANHA_EDITADA',
            usuario,
            {
                'campos': alterados,
                'anteriores': anteriores,
                'justificativa': justificativa.strip().upper(),
            },
        )
        cls._comunicar(
            campanha,
            usuario,
            f'CAMPANHA DE AUDITORIA ALTERADA: {campanha.nome}',
            f'CAMPOS ALTERADOS: {", ".join(alterados)}.',
            bases=list(campanha.auditorias_bases.values_list('base_id', flat=True)),
        )
        return campanha

    @classmethod
    @transaction.atomic
    def adicionar_bases(
        cls,
        *,
        campanha,
        bases,
        inicio_em,
        fim_em,
        usuario,
        observacoes='',
        justificativa='',
    ):
        exigir_admin(usuario)
        campanha = CampanhaAuditoria.objects.select_for_update().get(pk=campanha.pk)
        permitidos = {
            CampanhaAuditoria.Status.RASCUNHO,
            CampanhaAuditoria.Status.AGENDADA,
            CampanhaAuditoria.Status.EM_ANDAMENTO,
        }
        if campanha.status not in permitidos:
            raise ValidationError('O STATUS DA CAMPANHA NÃO PERMITE INCLUIR BASES.')
        if campanha.status == CampanhaAuditoria.Status.AGENDADA and campanha.auditorias_bases.filter(
            snapshot_criado_em__isnull=False
        ).exists():
            raise ValidationError('CAMPANHA JÁ INICIADA NÃO ACEITA INCLUSÃO SEM JUSTIFICATIVA.')
        if campanha.status == CampanhaAuditoria.Status.EM_ANDAMENTO:
            if not justificativa.strip():
                raise ValidationError('INCLUSÃO APÓS O INÍCIO EXIGE JUSTIFICATIVA.')
            if inicio_em <= timezone.now():
                raise ValidationError('BASE INCLUÍDA APÓS O INÍCIO DEVE TER DATA FUTURA.')

        bases_unicas = {base.pk: base for base in bases}
        existentes = set(
            campanha.auditorias_bases.filter(base_id__in=bases_unicas).values_list('base_id', flat=True)
        )
        candidatas = [base for pk, base in bases_unicas.items() if pk not in existentes]
        auditorias = []
        for base in candidatas:
            auditoria = AuditoriaBase(
                campanha=campanha,
                base=base,
                inicio_em=inicio_em,
                fim_em=fim_em,
                observacoes=(observacoes or '').upper(),
            )
            auditoria.full_clean(validate_unique=False)
            auditorias.append(auditoria)
        if not auditorias:
            return []

        AuditoriaBase.objects.bulk_create(auditorias)
        tipo_evento = (
            'BASE_ADICIONADA_APOS_INICIO_DA_CAMPANHA'
            if campanha.status == CampanhaAuditoria.Status.EM_ANDAMENTO
            else 'BASE_ADICIONADA'
        )
        for auditoria in auditorias:
            cls._evento(
                campanha,
                tipo_evento,
                usuario,
                {
                    'auditoria_base_id': auditoria.pk,
                    'base_id': auditoria.base_id,
                    'base': auditoria.base.nome,
                    'inicio_em': inicio_em.isoformat(),
                    'fim_em': fim_em.isoformat(),
                    'justificativa': justificativa.strip().upper(),
                },
            )
        cls._comunicar(
            campanha,
            usuario,
            f'BASES INCLUÍDAS NA AUDITORIA: {campanha.nome}',
            f'{len(auditorias)} BASE(S) INCLUÍDA(S) NA CAMPANHA.',
            bases=[auditoria.base for auditoria in auditorias],
        )
        return auditorias

    @classmethod
    def adicionar_base(cls, *, campanha, base, inicio_em, fim_em, usuario):
        auditorias = cls.adicionar_bases(
            campanha=campanha,
            bases=[base],
            inicio_em=inicio_em,
            fim_em=fim_em,
            usuario=usuario,
        )
        if not auditorias:
            raise ValidationError('A BASE JÁ PARTICIPA DESTA CAMPANHA.')
        return auditorias[0]

    @classmethod
    @transaction.atomic
    def agendar(cls, campanha, usuario):
        exigir_admin(usuario)
        campanha = CampanhaAuditoria.objects.select_for_update().get(pk=campanha.pk)
        if campanha.status != CampanhaAuditoria.Status.RASCUNHO:
            raise ValidationError('A CAMPANHA NÃO ESTÁ EM RASCUNHO.')
        if not campanha.auditorias_bases.exists():
            raise ValidationError('INCLUA AO MENOS UMA BASE ANTES DE AGENDAR.')
        campanha.status = CampanhaAuditoria.Status.AGENDADA
        campanha.save(update_fields=['status', 'atualizado_em'])
        cls._evento(campanha, 'CAMPANHA_AGENDADA', usuario)
        cls._comunicar(
            campanha,
            usuario,
            f'CAMPANHA DE AUDITORIA AGENDADA: {campanha.nome}',
            f'A CAMPANHA {campanha.nome} FOI AGENDADA.',
            bases=list(campanha.auditorias_bases.values_list('base_id', flat=True)),
        )
        return campanha

    @classmethod
    @transaction.atomic
    def atualizar_periodo_base(
        cls, auditoria_base, *, inicio_em, fim_em, usuario, justificativa=''
    ):
        exigir_admin(usuario)
        auditoria = AuditoriaBase.objects.select_for_update().select_related(
            'campanha', 'base'
        ).get(pk=auditoria_base.pk)
        if auditoria.campanha.status in {
            CampanhaAuditoria.Status.ENCERRADA,
            CampanhaAuditoria.Status.CANCELADA,
        } or auditoria.status in {
            AuditoriaBase.Status.FINALIZADA,
            AuditoriaBase.Status.DISPENSADA,
        }:
            raise ValidationError('ESTA AUDITORIA NÃO ACEITA ALTERAÇÃO DE PERÍODO.')
        exige_justificativa = (
            auditoria.campanha.status != CampanhaAuditoria.Status.RASCUNHO
            or bool(auditoria.snapshot_criado_em)
        )
        if exige_justificativa and not justificativa.strip():
            raise ValidationError('ALTERAÇÕES DE DATA APÓS O AGENDAMENTO EXIGEM JUSTIFICATIVA.')
        anteriores = {
            'inicio_em': auditoria.inicio_em.isoformat(),
            'fim_em': auditoria.fim_em.isoformat(),
        }
        auditoria.inicio_em = inicio_em
        auditoria.fim_em = fim_em
        auditoria.full_clean()
        auditoria.save(update_fields=['inicio_em', 'fim_em'])
        dados = {
            **anteriores,
            'novo_inicio_em': inicio_em.isoformat(),
            'novo_fim_em': fim_em.isoformat(),
            'justificativa': justificativa.strip().upper(),
        }
        cls._evento(
            auditoria.campanha,
            'PERIODO_BASE_ALTERADO',
            usuario,
            {'auditoria_base_id': auditoria.pk, 'base_id': auditoria.base_id, **dados},
        )
        if auditoria.snapshot_criado_em:
            AuditoriaEvento.objects.create(
                auditoria_base=auditoria,
                tipo='PERIODO_ALTERADO',
                usuario=usuario,
                dados=dados,
            )
        cls._comunicar(
            auditoria.campanha,
            usuario,
            f'PERÍODO DE AUDITORIA ALTERADO: {auditoria.base.nome}',
            f'O PERÍODO DA BASE {auditoria.base.nome} FOI ALTERADO.',
            bases=[auditoria.base],
        )
        return auditoria

    @staticmethod
    def _tem_atividade_operacional(auditoria):
        return bool(
            auditoria.snapshot_criado_em
            or auditoria.iniciada_em
            or auditoria.enviada_em
            or auditoria.finalizada_em
            or auditoria.versao_reabertura
            or auditoria.snapshot_equipamentos.exists()
            or auditoria.leituras.exists()
            or auditoria.divergencias.exists()
            or auditoria.eventos.exclude(tipo='PERIODO_ALTERADO').exists()
        )

    @classmethod
    @transaction.atomic
    def remover_base(cls, auditoria_base, usuario, justificativa=''):
        exigir_admin(usuario)
        auditoria = AuditoriaBase.objects.select_for_update().select_related(
            'campanha', 'base'
        ).get(pk=auditoria_base.pk)
        campanha = CampanhaAuditoria.objects.select_for_update().get(pk=auditoria.campanha_id)
        if campanha.status in {
            CampanhaAuditoria.Status.ENCERRADA,
            CampanhaAuditoria.Status.CANCELADA,
        }:
            raise ValidationError('CAMPANHA ENCERRADA OU CANCELADA NÃO ACEITA REMOÇÃO.')
        atividade = cls._tem_atividade_operacional(auditoria)
        if atividade:
            if not justificativa.strip():
                raise ValidationError('BASE COM ATIVIDADE EXIGE JUSTIFICATIVA PARA DISPENSA.')
            if auditoria.status in {
                AuditoriaBase.Status.FINALIZADA,
                AuditoriaBase.Status.DISPENSADA,
            }:
                raise ValidationError('ESTA BASE JÁ FOI ENCERRADA.')
            auditoria.status = AuditoriaBase.Status.DISPENSADA
            auditoria.observacoes = '\n'.join(filter(None, [
                auditoria.observacoes,
                f'DISPENSA: {justificativa.strip().upper()}',
            ]))
            auditoria.save(update_fields=['status', 'observacoes'])
            AuditoriaEvento.objects.create(
                auditoria_base=auditoria,
                tipo='BASE_DISPENSADA',
                usuario=usuario,
                dados={'justificativa': justificativa.strip().upper()},
            )
            modo = 'DISPENSADA'
        else:
            auditoria_id = auditoria.pk
            base_id = auditoria.base_id
            auditoria.delete()
            modo = 'EXCLUIDA'
            auditoria = None

        cls._evento(
            campanha,
            'BASE_REMOVIDA',
            usuario,
            {
                'auditoria_base_id': auditoria.pk if auditoria else auditoria_id,
                'base_id': auditoria.base_id if auditoria else base_id,
                'modo': modo,
                'justificativa': justificativa.strip().upper(),
            },
        )
        if campanha.status == CampanhaAuditoria.Status.AGENDADA and not campanha.auditorias_bases.exists():
            campanha.status = CampanhaAuditoria.Status.RASCUNHO
            campanha.save(update_fields=['status', 'atualizado_em'])
            cls._evento(
                campanha,
                'CAMPANHA_RETORNOU_RASCUNHO',
                usuario,
                {'motivo': 'ÚLTIMA BASE REMOVIDA.'},
            )
        cls._comunicar(
            campanha,
            usuario,
            f'BASE REMOVIDA DA AUDITORIA: {campanha.nome}',
            f'BASE REMOVIDA NO MODO {modo}.',
            bases=[base_id if not auditoria else auditoria.base],
        )
        return modo

    @classmethod
    def dispensar_base(cls, auditoria_base, usuario, justificativa):
        return cls.remover_base(auditoria_base, usuario, justificativa)

    @classmethod
    @transaction.atomic
    def encerrar_campanha(cls, campanha, usuario):
        exigir_admin(usuario)
        campanha = CampanhaAuditoria.objects.select_for_update().get(pk=campanha.pk)
        if campanha.status in {
            CampanhaAuditoria.Status.ENCERRADA,
            CampanhaAuditoria.Status.CANCELADA,
        }:
            raise ValidationError('A CAMPANHA JÁ FOI ENCERRADA.')
        pendentes = campanha.auditorias_bases.exclude(
            status__in=[
                AuditoriaBase.Status.FINALIZADA,
                AuditoriaBase.Status.EXPIRADA,
                AuditoriaBase.Status.DISPENSADA,
            ]
        )
        if pendentes.exists():
            raise ValidationError('TODAS AS BASES DEVEM ESTAR FINALIZADAS, EXPIRADAS OU DISPENSADAS.')
        campanha.status = CampanhaAuditoria.Status.ENCERRADA
        campanha.encerrado_em = timezone.now()
        campanha.save(update_fields=['status', 'encerrado_em', 'atualizado_em'])
        cls._evento(campanha, 'CAMPANHA_ENCERRADA', usuario)
        cls._comunicar(
            campanha,
            usuario,
            f'CAMPANHA DE AUDITORIA ENCERRADA: {campanha.nome}',
            f'A CAMPANHA {campanha.nome} FOI ENCERRADA.',
            bases=list(campanha.auditorias_bases.values_list('base_id', flat=True)),
        )
        return campanha

    @classmethod
    @transaction.atomic
    def cancelar_campanha(cls, campanha, usuario, justificativa):
        exigir_admin(usuario)
        if not justificativa.strip():
            raise ValidationError('INFORME A JUSTIFICATIVA DO CANCELAMENTO.')
        campanha = CampanhaAuditoria.objects.select_for_update().get(pk=campanha.pk)
        if campanha.status in {
            CampanhaAuditoria.Status.ENCERRADA,
            CampanhaAuditoria.Status.CANCELADA,
        }:
            raise ValidationError('CAMPANHA ENCERRADA OU CANCELADA NÃO PODE SER CANCELADA.')
        campanha.status = CampanhaAuditoria.Status.CANCELADA
        campanha.save(update_fields=['status', 'atualizado_em'])
        justificativa = justificativa.strip().upper()
        cls._evento(
            campanha,
            'CAMPANHA_CANCELADA',
            usuario,
            {'justificativa': justificativa},
        )
        for auditoria in campanha.auditorias_bases.all():
            AuditoriaEvento.objects.create(
                auditoria_base=auditoria,
                tipo='CAMPANHA_CANCELADA',
                usuario=usuario,
                dados={'justificativa': justificativa},
            )
        cls._comunicar(
            campanha,
            usuario,
            f'CAMPANHA DE AUDITORIA CANCELADA: {campanha.nome}',
            f'JUSTIFICATIVA: {justificativa}',
            bases=list(campanha.auditorias_bases.values_list('base_id', flat=True)),
            tipo='URGENTE',
        )
        return campanha

    @classmethod
    @transaction.atomic
    def reabrir_base(cls, auditoria_base, usuario, justificativa):
        exigir_admin(usuario)
        if not justificativa.strip():
            raise ValidationError('INFORME A JUSTIFICATIVA DA REABERTURA.')
        auditoria = AuditoriaBase.objects.select_for_update().select_related('campanha').get(
            pk=auditoria_base.pk
        )
        if not auditoria.snapshot_criado_em:
            raise ValidationError('NÃO É POSSÍVEL REABRIR UMA AUDITORIA AINDA NÃO INICIADA.')
        if auditoria.status not in (
            AuditoriaBase.Status.ENVIADA,
            AuditoriaBase.Status.COM_DIVERGENCIAS,
            AuditoriaBase.Status.EM_REGULARIZACAO,
            AuditoriaBase.Status.FINALIZADA,
        ):
            raise ValidationError('ESTA AUDITORIA NÃO ESTÁ EM UM ESTADO QUE PERMITA REABERTURA.')
        auditoria.status = AuditoriaBase.Status.REABERTA
        auditoria.versao_reabertura += 1
        auditoria.finalizada_em = None
        auditoria.finalizada_por = None
        auditoria.correcao_solicitada_em = None
        auditoria.correcao_solicitada_por = None
        auditoria.prazo_correcao_em = None
        auditoria.orientacoes_correcao = ''
        auditoria.save(update_fields=[
            'status', 'versao_reabertura', 'finalizada_em', 'finalizada_por',
            'correcao_solicitada_em', 'correcao_solicitada_por',
            'prazo_correcao_em', 'orientacoes_correcao',
        ])
        if auditoria.campanha.status != CampanhaAuditoria.Status.EM_ANDAMENTO:
            auditoria.campanha.status = CampanhaAuditoria.Status.EM_ANDAMENTO
            auditoria.campanha.encerrado_em = None
            auditoria.campanha.save(update_fields=['status', 'encerrado_em', 'atualizado_em'])
        justificativa = justificativa.strip().upper()
        AuditoriaEvento.objects.create(
            auditoria_base=auditoria,
            tipo='AUDITORIA_REABERTA',
            usuario=usuario,
            dados={'justificativa': justificativa, 'versao': auditoria.versao_reabertura},
        )
        cls._evento(
            auditoria.campanha,
            'AUDITORIA_BASE_REABERTA',
            usuario,
            {
                'auditoria_base_id': auditoria.pk,
                'base_id': auditoria.base_id,
                'justificativa': justificativa,
                'versao': auditoria.versao_reabertura,
            },
        )
        return auditoria

    @staticmethod
    @transaction.atomic
    def sincronizar_status_por_data(campanha=None):
        agora = timezone.now()
        qs = AuditoriaBase.objects.select_for_update().filter(
            status__in=[AuditoriaBase.Status.NAO_INICIADA, AuditoriaBase.Status.DISPONIVEL]
        )
        if campanha:
            qs = qs.filter(campanha=campanha)
        qs.filter(inicio_em__lte=agora, fim_em__gte=agora).update(
            status=AuditoriaBase.Status.DISPONIVEL
        )
        qs.filter(fim_em__lt=agora).update(status=AuditoriaBase.Status.EXPIRADA)
