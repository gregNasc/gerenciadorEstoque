from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from chamados.models import (
    Chamado,
    ChamadoAnexo,
    ChamadoAvaliacao,
    ChamadoEvento,
    ChamadoMensagem,
    ChamadoSessaoAtendimento,
    ChamadoTransferenciaAtendente,
    SequenciaChamado,
)
from chamados.policies import ChamadoAccessPolicy
from estoque.services.comunicado_service import ComunicadoService


class ChamadoService:
    STATUS_PAUSA = {
        Chamado.Status.AGUARDANDO_SOLICITANTE,
        Chamado.Status.AGUARDANDO_TERCEIRO,
    }
    TERMINAIS = {Chamado.Status.ENCERRADO, Chamado.Status.CANCELADO}

    @classmethod
    def status_permitidos(cls, chamado, user):
        if chamado.aberto_por_id == getattr(user, 'pk', None) and not ChamadoAccessPolicy.pode_atender(user):
            return {Chamado.Status.CANCELADO} if chamado.status in {
                Chamado.Status.ABERTO, Chamado.Status.AGUARDANDO_ATENDIMENTO,
            } else set()
        if chamado.atendente_id != getattr(user, 'pk', None) and not ChamadoAccessPolicy.pode_supervisionar(user):
            return set()
        mapa = {
            Chamado.Status.EM_ATENDIMENTO: {
                Chamado.Status.AGUARDANDO_SOLICITANTE,
                Chamado.Status.AGUARDANDO_TERCEIRO,
                Chamado.Status.RESOLVIDO,
                Chamado.Status.CANCELADO,
            },
            Chamado.Status.AGUARDANDO_SOLICITANTE: {
                Chamado.Status.EM_ATENDIMENTO, Chamado.Status.CANCELADO,
            },
            Chamado.Status.AGUARDANDO_TERCEIRO: {
                Chamado.Status.EM_ATENDIMENTO, Chamado.Status.CANCELADO,
            },
            Chamado.Status.REABERTO: {
                Chamado.Status.EM_ATENDIMENTO, Chamado.Status.CANCELADO,
            },
        }
        return mapa.get(chamado.status, set())

    @staticmethod
    def _envolvidos(chamado):
        return [chamado.aberto_por, chamado.atendente]

    @staticmethod
    def _evento(chamado, tipo, descricao, usuario, dados=None):
        evento = ChamadoEvento.objects.create(
            chamado=chamado, tipo=tipo, descricao=descricao,
            usuario=usuario, dados=dados or {},
        )
        payload = {
            'id': evento.pk,
            'chamado_id': chamado.pk,
            'protocolo': chamado.protocolo,
            'tipo': tipo,
            'descricao': descricao,
            'url': f'/chamados/{chamado.pk}/',
            'autor_id': getattr(usuario, 'pk', None),
            'autor': (
                usuario.get_full_name() or usuario.get_username()
                if usuario else ''
            ),
        }
        grupos = {'chamados_admins'}
        if tipo == 'ABERTURA':
            grupos.add('chamados_atendentes')
        elif tipo not in {'AVALIACAO', 'NOTA_INTERNA'}:
            grupos.add(f'chamados_usuario_{chamado.aberto_por_id}')
            if chamado.atendente_id:
                grupos.add(f'chamados_usuario_{chamado.atendente_id}')

        def publicar():
            camada = get_channel_layer()
            if not camada:
                return
            for grupo in grupos:
                async_to_sync(camada.group_send)(
                    grupo,
                    {'type': 'chamado.evento', 'payload': payload},
                )

        transaction.on_commit(publicar)
        return evento

    @staticmethod
    def _comunicar(
        chamado, usuario, titulo, mensagem, tipo='OPERACIONAL',
        evento='ATUALIZACAO', dados=None, incluir_fila=False,
    ):
        metadados = {
            'template_codigo': 'chamado_acao',
            'evento_codigo': evento,
            'chamado_id': chamado.pk,
        }
        metadados.update(dados or {})
        destinatarios = ChamadoService._envolvidos(chamado)
        if incluir_fila:
            destinatarios.extend(ChamadoAccessPolicy.atendentes_para(chamado))
        return ComunicadoService.criar_acao(
            titulo=titulo,
            mensagem=mensagem,
            usuario=usuario,
            usuarios=destinatarios,
            bases=None,
            empresa=chamado.empresa,
            tipo=tipo,
            dados=metadados,
            url=f'/chamados/{chamado.pk}/',
        )

    @classmethod
    def _abrir_sessao(cls, chamado, atendente, usuario):
        if chamado.sessoes.filter(encerrada_em__isnull=True).exists():
            raise ValidationError('JÁ EXISTE UMA SESSÃO DE ATENDIMENTO ABERTA.')
        try:
            sessao = ChamadoSessaoAtendimento.objects.create(
                chamado=chamado, atendente=atendente,
            )
        except IntegrityError as exc:
            raise ValidationError('JÁ EXISTE UMA SESSÃO DE ATENDIMENTO ABERTA.') from exc
        cls._evento(
            chamado, 'SESSAO_INICIADA', 'SESSÃO DE ATENDIMENTO INICIADA.', usuario,
            {'sessao_id': sessao.pk, 'atendente_id': atendente.pk},
        )
        return sessao

    @classmethod
    def _fechar_sessao(cls, chamado, usuario, motivo):
        sessao = chamado.sessoes.select_for_update().filter(encerrada_em__isnull=True).first()
        if not sessao:
            return None
        sessao.encerrada_em = timezone.now()
        sessao.motivo_encerramento = motivo
        sessao.encerrada_por = usuario
        sessao.full_clean()
        sessao.save(update_fields=['encerrada_em', 'motivo_encerramento', 'encerrada_por'])
        cls._evento(
            chamado, 'SESSAO_ENCERRADA', 'SESSÃO DE ATENDIMENTO ENCERRADA.', usuario,
            {'sessao_id': sessao.pk, 'motivo': motivo},
        )
        return sessao

    @classmethod
    @transaction.atomic
    def abrir(cls, *, usuario, **dados):
        base = dados['base']
        inventario = dados.get('inventario')

        hoje = timezone.localdate()

       # INVENTÁRIO
        if not inventario:
            raise ValidationError({
                'inventario':
                    'O INVENTÁRIO É OBRIGATÓRIO PARA ABRIR UM CHAMADO.'
            })

        # Usuário precisa possuir acesso à base.
        if not ChamadoAccessPolicy.pode_abrir_na_base(
                usuario,
                base,
        ):
            raise PermissionDenied(
                'VOCÊ NÃO POSSUI ACESSO A ESTA BASE.'
            )

        # Inventário precisa pertencer à base.
        if inventario.base_id != base.pk:
            raise ValidationError({
                'inventario':
                    'O INVENTÁRIO NÃO PERTENCE À BASE INFORMADA.'
            })

        # Inventário precisa ser do dia atual.
        if (
            inventario.lider_usuario_id
            and inventario.lider_usuario_id != usuario.pk
            and not getattr(usuario.perfil, 'is_gestor', False)
        ):
            raise PermissionDenied(
                'SOMENTE O LIDER VINCULADO AO INVENTARIO PODE ABRIR ESTE CHAMADO.'
            )

        if inventario.data_inicio != hoje:
            raise ValidationError({
                'inventario':
                    'SÓ É POSSÍVEL ABRIR CHAMADOS PARA INVENTÁRIOS DO DIA ATUAL.'
            })

        # Permitimos planejado ou em andamento.
        status_permitidos = {
            'PLANEJADO',
            'EM_ANDAMENTO',
        }

        if inventario.status not in status_permitidos:
            raise ValidationError({
                'inventario':
                    'SÓ É POSSÍVEL ABRIR CHAMADOS PARA INVENTÁRIOS PLANEJADOS OU EM ANDAMENTO.'
            })

       # DADOS HERDADOS DO INVENTÁRIO
        # Loja sempre vem do inventário.
        dados['momento_inventario_abertura'] = (
            Chamado.MomentoInventario.EM_ANDAMENTO
            if inventario.status == 'EM_ANDAMENTO'
            else Chamado.MomentoInventario.ANTES
        )

        dados['loja'] = (
                inventario.loja or ''
        ).strip()

        # Líder vem do inventário,
        # mas preservamos alteração manual feita no formulário.
        dados['lider'] = (
                dados.get('lider')
                or inventario.lider
                or ''
        ).strip()

       # CATEGORIA DO EQUIPAMENTO
        equipamento = dados.get('equipamento')
        categoria_equipamento = (
                dados.get('categoria_equipamento')
                or (
                    equipamento.produto.categoria
                    if equipamento and equipamento.produto_id
                    else 'Sistema'
                )
        ).strip()
        dados['categoria_equipamento'] = categoria_equipamento

        if not categoria_equipamento:
            raise ValidationError({
                'categoria_equipamento':
                    'INFORME A CATEGORIA DO EQUIPAMENTO.'
            })

       # EQUIPAMENTO (OPCIONAL PARA SISTEMA / SOFTWARE)
        if categoria_equipamento != 'Sistema' and not equipamento:
            raise ValidationError({
                'equipamento':
                    'INFORME O EQUIPAMENTO DO CHAMADO.'
            })

        # Equipamento precisa pertencer à base.
        if equipamento and equipamento.regional_id != base.pk:
            raise ValidationError({
                'equipamento':
                    'O EQUIPAMENTO NÃO PERTENCE À BASE INFORMADA.'
            })

        # Equipamento precisa possuir produto.
        if equipamento and not equipamento.produto:
            raise ValidationError({
                'equipamento':
                    'O EQUIPAMENTO NÃO POSSUI PRODUTO VINCULADO.'
            })

        # Categoria escolhida precisa ser a categoria real
        # do produto vinculado ao equipamento.
        if (
                equipamento
                and equipamento.produto.categoria
                != categoria_equipamento
        ):
            raise ValidationError({
                'equipamento':
                    'O EQUIPAMENTO NÃO PERTENCE À CATEGORIA INFORMADA.'
            })

       # SEQUÊNCIA DO PROTOCOLO
        ano = hoje.year

        sequencia, _ = (
            SequenciaChamado.objects
            .select_for_update()
            .get_or_create(
                empresa=base.empresa,
                ano=ano,
            )
        )

        sequencia.ultimo_numero += 1

        sequencia.save(
            update_fields=['ultimo_numero']
        )

       # CRIAÇÃO DO CHAMADO
        chamado = Chamado(
            protocolo=(
                f'CH-{ano}-'
                f'{base.empresa_id:04d}-'
                f'{sequencia.ultimo_numero:06d}'
            ),
            empresa=base.empresa,
            aberto_por=usuario,
            status=Chamado.Status.AGUARDANDO_ATENDIMENTO,
            **dados,
        )

        chamado.definir_prazo_sla()
        chamado.full_clean()
        chamado.save()

       # HISTÓRICO
        cls._evento(
            chamado,
            'ABERTURA',
            'CHAMADO ABERTO.',
            usuario,
        )

        cls._evento(
            chamado,
            'ENTRADA_FILA',
            'CHAMADO ENCAMINHADO À FILA DE ATENDIMENTO.',
            usuario,
            {
                'status': chamado.status,
            },
        )

       # COMUNICAÇÃO
        cls._comunicar(
            chamado,
            usuario,
            f'NOVO CHAMADO {chamado.protocolo}',
            (
                f'{chamado.titulo}\n'
                f'BASE: {chamado.base.nome}\n'
                f'PRIORIDADE: {chamado.get_prioridade_display()}'
            ),
            tipo=(
                'URGENTE'
                if chamado.prioridade in {
                    Chamado.Prioridade.ALTA,
                    Chamado.Prioridade.CRITICA,
                }
                else 'OPERACIONAL'
            ),
            evento='ABERTURA', incluir_fila=True,
        )

        return chamado

    @classmethod
    @transaction.atomic
    def assumir(cls, chamado, usuario):
        chamado = Chamado.objects.select_for_update().select_related('base').get(pk=chamado.pk)
        if not ChamadoAccessPolicy.pode_atender(usuario):
            raise PermissionDenied('VOCÊ NÃO PODE ATENDER CHAMADOS.')
        if not ChamadoAccessPolicy.bases(usuario).filter(pk=chamado.base_id).exists() and not ChamadoAccessPolicy.e_admin(usuario):
            raise PermissionDenied('O CHAMADO ESTÁ FORA DO SEU ESCOPO DE BASES.')
        if chamado.atendente_id:
            raise ValidationError('O CHAMADO JÁ POSSUI ATENDENTE.')
        if chamado.status not in {
            Chamado.Status.ABERTO, Chamado.Status.AGUARDANDO_ATENDIMENTO,
            Chamado.Status.REABERTO,
        }:
            raise ValidationError('O CHAMADO NÃO ESTÁ DISPONÍVEL PARA ACEITE.')
        agora = timezone.now()
        chamado.atendente = usuario
        chamado.status = Chamado.Status.EM_ATENDIMENTO
        chamado.aceito_em = agora
        chamado.iniciado_em = chamado.iniciado_em or agora
        chamado.primeira_resposta_em = chamado.primeira_resposta_em or agora
        chamado.save(update_fields=[
            'atendente', 'status', 'aceito_em', 'iniciado_em',
            'primeira_resposta_em', 'atualizado_em',
        ])
        cls._abrir_sessao(chamado, usuario, usuario)
        cls._evento(
            chamado, 'ATRIBUICAO', f'CHAMADO ASSUMIDO POR {usuario.get_username()}.', usuario,
            {'atendente_id': usuario.pk, 'status_novo': chamado.status},
        )
        cls._evento(chamado, 'PRIMEIRA_RESPOSTA', 'PRIMEIRA RESPOSTA REGISTRADA.', usuario)
        return chamado

    @classmethod
    @transaction.atomic
    def adicionar_mensagem(cls, chamado, usuario, texto, nota_interna=False, anexo=None):
        chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
        if chamado.status in cls.TERMINAIS:
            raise ValidationError('CHAMADO ENCERRADO NÃO ACEITA NOVAS MENSAGENS.')
        if not chamado.atendente_id:
            raise ValidationError('O ATENDIMENTO PRECISA SER ASSUMIDO ANTES DO CHAT.')
        if not ChamadoAccessPolicy.pode_interagir(usuario, chamado):
            raise PermissionDenied('VOCÊ NÃO PODE INTERAGIR NESTE CHAMADO.')
        if nota_interna and not ChamadoAccessPolicy.pode_atender(usuario):
            raise PermissionDenied('APENAS ATENDENTES PODEM CRIAR NOTAS INTERNAS.')
        mensagem = ChamadoMensagem(
            chamado=chamado, autor=usuario, texto=texto, nota_interna=nota_interna
        )
        mensagem.full_clean()
        mensagem.save()
        if anexo:
            registro = ChamadoAnexo(
                chamado=chamado, mensagem=mensagem, arquivo=anexo,
                nome_original=anexo.name, enviado_por=usuario,
            )
            registro.full_clean()
            registro.save()
            cls._evento(
                chamado, 'ANEXO', 'ANEXO ADICIONADO AO CHAMADO.', usuario,
                {'anexo_id': registro.pk, 'mensagem_id': mensagem.pk},
            )
        if chamado.atendente_id == usuario.pk and not chamado.primeira_resposta_em:
            chamado.primeira_resposta_em = timezone.now()
            chamado.save(update_fields=['primeira_resposta_em', 'atualizado_em'])
            cls._evento(chamado, 'PRIMEIRA_RESPOSTA', 'PRIMEIRA RESPOSTA REGISTRADA.', usuario)
        if (
            chamado.status == Chamado.Status.AGUARDANDO_SOLICITANTE
            and chamado.aberto_por_id == usuario.pk
        ):
            chamado.status = Chamado.Status.EM_ATENDIMENTO
            chamado.save(update_fields=['status', 'atualizado_em'])
            if chamado.atendente_id:
                cls._abrir_sessao(chamado, chamado.atendente, usuario)
            cls._evento(
                chamado, 'RETORNO_SOLICITANTE', 'SOLICITANTE RESPONDEU AO CHAMADO.', usuario,
                {'status_novo': chamado.status},
            )
        cls._evento(
            chamado, 'NOTA_INTERNA' if nota_interna else 'MENSAGEM',
            'NOTA INTERNA ADICIONADA.' if nota_interna else 'NOVA MENSAGEM NO CHAMADO.',
            usuario, {'mensagem_id': mensagem.pk},
        )
        return mensagem

    @classmethod
    @transaction.atomic
    def alterar_status(cls, chamado, usuario, status, resolucao='', causa_raiz=''):
        chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
        if status not in cls.status_permitidos(chamado, usuario):
            raise PermissionDenied('TRANSIÇÃO DE STATUS NÃO AUTORIZADA.')
        if status == Chamado.Status.RESOLVIDO:
            return cls.resolver(chamado, usuario, causa_raiz=causa_raiz, solucao=resolucao)
        anterior = chamado.status
        if status in cls.STATUS_PAUSA:
            cls._fechar_sessao(chamado, usuario, status)
        elif status == Chamado.Status.EM_ATENDIMENTO:
            if not chamado.atendente_id:
                raise ValidationError('O CHAMADO NÃO POSSUI ATENDENTE.')
            cls._abrir_sessao(chamado, chamado.atendente, usuario)
        elif status == Chamado.Status.CANCELADO:
            cls._fechar_sessao(chamado, usuario, 'CANCELADO')
            chamado.fechado_em = timezone.now()
        chamado.status = status
        chamado.save()
        cls._evento(
            chamado, 'STATUS', f'STATUS ALTERADO DE {anterior} PARA {status}.', usuario,
            {'status_anterior': anterior, 'status_novo': status, 'justificativa': resolucao},
        )
        if status == Chamado.Status.CANCELADO:
            cls._comunicar(
                chamado, usuario, f'CHAMADO {chamado.protocolo} CANCELADO',
                resolucao or 'O CHAMADO FOI CANCELADO.',
                tipo='URGENTE', evento='ENCERRAMENTO',
                dados={'status': chamado.status},
            )
        return chamado

    @classmethod
    @transaction.atomic
    def resolver(cls, chamado, usuario, *, causa_raiz, solucao):
        chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
        if chamado.atendente_id != usuario.pk and not ChamadoAccessPolicy.pode_supervisionar(usuario):
            raise PermissionDenied('APENAS O ATENDENTE OU SUPERVISOR PODE RESOLVER O CHAMADO.')
        if chamado.status not in {
            Chamado.Status.EM_ATENDIMENTO,
            Chamado.Status.AGUARDANDO_SOLICITANTE,
            Chamado.Status.AGUARDANDO_TERCEIRO,
            Chamado.Status.REABERTO,
        }:
            raise ValidationError('O CHAMADO NÃO ESTÁ EM ESTADO DE RESOLUÇÃO.')
        causa_raiz = (causa_raiz or '').strip()
        solucao = (solucao or '').strip()
        if not causa_raiz or not solucao:
            raise ValidationError('CAUSA RAIZ E SOLUÇÃO SÃO OBRIGATÓRIAS.')
        cls._fechar_sessao(chamado, usuario, 'RESOLVIDO')
        agora = timezone.now()
        anterior = chamado.status
        chamado.causa_raiz = causa_raiz
        chamado.resolucao = solucao
        chamado.resolvido_em = agora
        chamado.status = Chamado.Status.AVALIACAO
        chamado.full_clean()
        chamado.save()
        cls._evento(
            chamado, 'CAUSA_E_SOLUCAO', 'CAUSA RAIZ E SOLUÇÃO REGISTRADAS.', usuario,
            {'causa_raiz': chamado.causa_raiz, 'solucao': chamado.resolucao},
        )
        cls._evento(
            chamado, 'RESOLUCAO', 'CHAMADO RESOLVIDO E ENVIADO PARA AVALIAÇÃO.', usuario,
            {'status_anterior': anterior, 'status_novo': chamado.status},
        )
        cls._comunicar(
            chamado, usuario, f'ATENDIMENTO {chamado.protocolo} CONCLUÍDO',
            f'SOLUÇÃO INFORMADA: {chamado.resolucao}. AVALIE O ATENDIMENTO.',
            evento='ENCERRAMENTO',
            dados={'status': chamado.status},
        )
        return chamado

    @classmethod
    @transaction.atomic
    def avaliar(cls, chamado, usuario, *, nota, resolvido, comentario=''):
        chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
        if chamado.aberto_por_id != usuario.pk:
            raise PermissionDenied('SOMENTE O SOLICITANTE PODE AVALIAR O CHAMADO.')
        if chamado.status != Chamado.Status.AVALIACAO:
            raise ValidationError('O CHAMADO NÃO ESTÁ AGUARDANDO AVALIAÇÃO.')
        atendimento = chamado.sessoes.filter(
            encerrada_em__isnull=False,
            motivo_encerramento='RESOLVIDO',
        ).order_by('-encerrada_em', '-pk').first()
        if not atendimento:
            raise ValidationError('NÃO EXISTE ATENDIMENTO RESOLVIDO PARA RECEBER A NOTA.')
        avaliacao = ChamadoAvaliacao.objects.filter(atendimento=atendimento).first()
        if avaliacao:
            avaliacao.nota = nota
            avaliacao.resolvido = bool(resolvido)
            avaliacao.comentario = comentario
            avaliacao.full_clean()
            avaliacao.save(update_fields=['nota', 'resolvido', 'comentario', 'atualizada_em'])
        else:
            avaliacao = ChamadoAvaliacao(
                chamado=chamado, atendimento=atendimento,
                solicitante=usuario, nota=nota,
                resolvido=bool(resolvido), comentario=comentario,
            )
            avaliacao.full_clean()
            avaliacao.save()
        cls._evento(
            chamado, 'AVALIACAO', 'AVALIAÇÃO DO SOLICITANTE REGISTRADA.', usuario,
            {
                'avaliacao_id': avaliacao.pk, 'atendimento_id': atendimento.pk,
                'atendente_id': atendimento.atendente_id,
                'nota': nota, 'resolvido': bool(resolvido),
            },
        )
        if resolvido:
            chamado.status = Chamado.Status.ENCERRADO
            chamado.fechado_em = timezone.now()
            evento = 'ENCERRAMENTO'
            mensagem = 'CHAMADO ENCERRADO APÓS AVALIAÇÃO POSITIVA.'
        else:
            chamado.status = Chamado.Status.REABERTO
            chamado.fechado_em = None
            evento = 'REABERTURA_AVALIACAO'
            mensagem = 'CHAMADO REABERTO APÓS AVALIAÇÃO NEGATIVA.'
        chamado.save(update_fields=['status', 'fechado_em', 'atualizado_em'])
        cls._evento(
            chamado, evento, mensagem, usuario,
            {'avaliacao_id': avaliacao.pk, 'atendimento_id': atendimento.pk},
        )
        admins = User.objects.filter(is_active=True, perfil__role='admin').distinct()
        ComunicadoService.criar_acao(
            titulo=f'NOTA DO ATENDIMENTO {chamado.protocolo}',
            mensagem=(
                f'NOTA: {nota}/5. '
                f'ATENDENTE: {atendimento.atendente.get_full_name() or atendimento.atendente.get_username()}. '
                f'{comentario or "SEM COMENTÁRIO."}'
            ),
            usuario=usuario,
            usuarios=admins,
            incluir_admins=True,
            incluir_autor=False,
            empresa=chamado.empresa,
            tipo='URGENTE' if not resolvido else 'OPERACIONAL',
            dados={
                'template_codigo': 'chamado_nota_admin',
                'evento_codigo': 'NOTA_ATENDIMENTO',
                'chamado_id': chamado.pk,
                'avaliacao_id': avaliacao.pk,
                'atendimento_id': atendimento.pk,
                'atendente_id': atendimento.atendente_id,
                'nota': nota,
                'resolvido': bool(resolvido),
            },
            url=f'/chamados/{chamado.pk}/',
        )
        return avaliacao

    @classmethod
    @transaction.atomic
    def transferir_atendente(cls, chamado, usuario, *, atendente_novo, motivo):
        chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
        if not ChamadoAccessPolicy.pode_transferir(usuario, chamado):
            raise PermissionDenied('VOCÊ NÃO PODE TRANSFERIR ESTE CHAMADO.')
        if not motivo.strip():
            raise ValidationError('INFORME O MOTIVO DA TRANSFERÊNCIA.')
        if atendente_novo.pk == chamado.atendente_id:
            raise ValidationError('SELECIONE UM ATENDENTE DIFERENTE.')
        if not ChamadoAccessPolicy.pode_atender(atendente_novo):
            raise ValidationError('O DESTINATÁRIO NÃO POSSUI PERFIL DE ATENDIMENTO.')
        if not ChamadoAccessPolicy.atendentes_online_para(chamado).filter(pk=atendente_novo.pk).exists():
            raise ValidationError('O NOVO ATENDENTE PRECISA ESTAR ONLINE.')
        if not ChamadoAccessPolicy.bases(atendente_novo).filter(pk=chamado.base_id).exists() and not ChamadoAccessPolicy.e_admin(atendente_novo):
            raise ValidationError('O NOVO ATENDENTE NÃO POSSUI ACESSO À BASE.')
        anterior = chamado.atendente
        cls._fechar_sessao(chamado, usuario, 'TRANSFERENCIA')
        transferencia = ChamadoTransferenciaAtendente.objects.create(
            chamado=chamado, atendente_anterior=anterior, atendente_novo=atendente_novo,
            motivo=motivo, transferido_por=usuario,
        )
        chamado.atendente = atendente_novo
        chamado.status = Chamado.Status.EM_ATENDIMENTO
        chamado.save(update_fields=['atendente', 'status', 'atualizado_em'])
        cls._abrir_sessao(chamado, atendente_novo, usuario)
        cls._evento(
            chamado, 'TRANSFERENCIA_ATENDENTE', 'ATENDIMENTO TRANSFERIDO.', usuario,
            {
                'transferencia_id': transferencia.pk,
                'atendente_anterior_id': anterior.pk if anterior else None,
                'atendente_novo_id': atendente_novo.pk,
                'motivo': motivo,
            },
        )
        return transferencia

    @classmethod
    @transaction.atomic
    def converter_em_sick(cls, chamado, usuario, *, diagnostico):
        # ``equipamento`` is nullable. PostgreSQL refuses a FOR UPDATE over the
        # nullable side of the LEFT OUTER JOIN generated by select_related.
        # Lock only the chamado row; SickService applies its own lock to the
        # equipment while performing the state transition.
        chamado = (
            Chamado.objects
            .select_for_update(of=('self',))
            .select_related('equipamento')
            .get(pk=chamado.pk)
        )
        if not ChamadoAccessPolicy.pode_converter_sick(usuario, chamado):
            raise PermissionDenied('VOCÊ NÃO PODE CONVERTER ESTE CHAMADO EM SICK.')
        if chamado.sick_id:
            raise ValidationError('O CHAMADO JÁ POSSUI SICK VINCULADO.')
        diagnostico = (diagnostico or '').strip()
        if not diagnostico:
            raise ValidationError('INFORME O DIAGNÓSTICO PARA O SICK.')
        from estoque.services.sick_service import SickService

        sick = SickService.marcar_como_sick(
            equipamento_id=chamado.equipamento_id,
            usuario=usuario,
            categoria='CHAMADO DE SUPORTE',
            motivo=chamado.titulo,
            observacao=diagnostico,
        )
        chamado.sick = sick
        chamado.save(update_fields=['sick', 'atualizado_em'])
        cls._evento(
            chamado, 'SICK_CRIADO', 'CHAMADO CONVERTIDO EM SICK.', usuario,
            {'sick_id': sick.pk, 'diagnostico': diagnostico},
        )
        return sick

    @classmethod
    def metricas(cls, chamado):
        agora = timezone.now()
        fim = chamado.fechado_em or chamado.resolvido_em or agora

        def sem_microssegundos(valor):
            if valor is None:
                return None

            return valor - timedelta(
                microseconds=valor.microseconds
            )

        suporte = timedelta()

        for sessao in chamado.sessoes.all():
            suporte += (
                    (sessao.encerrada_em or agora)
                    - sessao.iniciada_em
            )

        return {
            'espera_primeira_resposta': sem_microssegundos(
                chamado.primeira_resposta_em - chamado.aberto_em
                if chamado.primeira_resposta_em
                else None
            ),

            'tempo_aceite': sem_microssegundos(
                chamado.aceito_em - chamado.aberto_em
                if chamado.aceito_em
                else None
            ),

            'tempo_resolucao': sem_microssegundos(
                fim - chamado.aberto_em
            ),

            'suporte_efetivo': sem_microssegundos(
                suporte
            ),

            'transferencias':
                chamado.transferencias_atendente.count(),

            'reaberturas':
                chamado.eventos.filter(
                    tipo__startswith='REABERTURA'
                ).count(),
        }
