from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from chamados.models import (
    Chamado,
    ChamadoAnexo,
    ChamadoEvento,
    ChamadoMensagem,
    SequenciaChamado,
)
from chamados.policies import ChamadoAccessPolicy
from estoque.services.comunicado_service import ComunicadoService


class ChamadoService:
    TRANSICOES = {
        Chamado.Status.ABERTO: {Chamado.Status.EM_ATENDIMENTO, Chamado.Status.CANCELADO},
        Chamado.Status.EM_ATENDIMENTO: {
            Chamado.Status.AGUARDANDO_USUARIO,
            Chamado.Status.RESOLVIDO,
            Chamado.Status.CANCELADO,
        },
        Chamado.Status.AGUARDANDO_USUARIO: {
            Chamado.Status.EM_ATENDIMENTO,
            Chamado.Status.RESOLVIDO,
            Chamado.Status.CANCELADO,
        },
        Chamado.Status.RESOLVIDO: {Chamado.Status.FECHADO, Chamado.Status.EM_ATENDIMENTO},
        Chamado.Status.FECHADO: {Chamado.Status.EM_ATENDIMENTO},
        Chamado.Status.CANCELADO: {Chamado.Status.ABERTO},
    }

    @classmethod
    def status_permitidos(cls, chamado, user):
        permitidos = set(cls.TRANSICOES.get(chamado.status, set()))
        if ChamadoAccessPolicy.pode_atender(user):
            return permitidos
        if chamado.aberto_por_id != user.pk:
            return set()
        return permitidos & {
            Chamado.Status.FECHADO,
            Chamado.Status.EM_ATENDIMENTO,
            Chamado.Status.CANCELADO,
        }

    @staticmethod
    def _envolvidos(chamado):
        return [chamado.aberto_por, chamado.atendente]

    @staticmethod
    def _evento(chamado, tipo, descricao, usuario, dados=None):
        return ChamadoEvento.objects.create(
            chamado=chamado,
            tipo=tipo,
            descricao=descricao,
            usuario=usuario,
            dados=dados or {},
        )

    @staticmethod
    def _comunicar(chamado, usuario, titulo, mensagem, tipo='OPERACIONAL', interno=False):
        return ComunicadoService.criar_acao(
            titulo=titulo,
            mensagem=mensagem,
            usuario=usuario,
            usuarios=[chamado.atendente] if interno else ChamadoService._envolvidos(chamado),
            bases=None if interno else [chamado.base],
            empresa=chamado.empresa,
            tipo=tipo,
            dados={'template_codigo': 'chamado_acao', 'chamado_id': chamado.pk},
            url=f'/chamados/{chamado.pk}/',
        )

    @classmethod
    @transaction.atomic
    def abrir(cls, *, usuario, **dados):
        base = dados['base']
        if not ChamadoAccessPolicy.pode_abrir_na_base(usuario, base):
            raise PermissionDenied('VOCÊ NÃO POSSUI ACESSO A ESTA BASE.')
        ano = timezone.localdate().year
        sequencia, _ = SequenciaChamado.objects.select_for_update().get_or_create(
            empresa=base.empresa, ano=ano
        )
        sequencia.ultimo_numero += 1
        sequencia.save(update_fields=['ultimo_numero'])
        chamado = Chamado(
            protocolo=f'CH-{ano}-{base.empresa_id:04d}-{sequencia.ultimo_numero:06d}',
            empresa=base.empresa,
            aberto_por=usuario,
            **dados,
        )
        chamado.definir_prazo_sla()
        chamado.full_clean()
        chamado.save()
        cls._evento(chamado, 'ABERTURA', 'CHAMADO ABERTO.', usuario)
        cls._comunicar(
            chamado,
            usuario,
            f'NOVO CHAMADO {chamado.protocolo}',
            f'{chamado.titulo}\nBASE: {chamado.base.nome}\nPRIORIDADE: {chamado.get_prioridade_display()}',
            tipo='URGENTE' if chamado.prioridade in {Chamado.Prioridade.ALTA, Chamado.Prioridade.CRITICA} else 'OPERACIONAL',
        )
        return chamado

    @classmethod
    @transaction.atomic
    def assumir(cls, chamado, usuario):
        chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
        if not ChamadoAccessPolicy.pode_atender(usuario):
            raise PermissionDenied('VOCÊ NÃO PODE ATENDER CHAMADOS.')
        if chamado.atendente_id and chamado.atendente_id != usuario.pk:
            perfil = getattr(usuario, 'perfil', None)
            if not (usuario.is_superuser or (perfil and perfil.is_admin)):
                raise ValidationError('O CHAMADO JÁ POSSUI OUTRO ATENDENTE.')
        status_anterior = chamado.status
        chamado.atendente = usuario
        if chamado.status == Chamado.Status.ABERTO:
            chamado.status = Chamado.Status.EM_ATENDIMENTO
            chamado.iniciado_em = timezone.now()
        chamado.full_clean()
        chamado.save(update_fields=['atendente', 'status', 'iniciado_em', 'atualizado_em'])
        cls._evento(
            chamado, 'ATENDIMENTO', f'CHAMADO ASSUMIDO POR {usuario.get_username()}.', usuario,
            {'status_anterior': status_anterior, 'status_novo': chamado.status},
        )
        cls._comunicar(
            chamado, usuario, f'CHAMADO {chamado.protocolo} EM ATENDIMENTO',
            f'{usuario.get_full_name() or usuario.get_username()} INICIOU O ATENDIMENTO.',
        )
        return chamado

    @classmethod
    @transaction.atomic
    def adicionar_mensagem(cls, chamado, usuario, texto, nota_interna=False, anexo=None):
        chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
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
                chamado=chamado,
                mensagem=mensagem,
                arquivo=anexo,
                nome_original=anexo.name,
                enviado_por=usuario,
            )
            registro.full_clean()
            registro.save()
        cls._evento(
            chamado,
            'NOTA_INTERNA' if nota_interna else 'MENSAGEM',
            'NOTA INTERNA ADICIONADA.' if nota_interna else 'NOVA MENSAGEM NO CHAMADO.',
            usuario,
        )
        cls._comunicar(
            chamado,
            usuario,
            f'ATUALIZAÇÃO NO CHAMADO {chamado.protocolo}',
            'UMA NOTA INTERNA FOI REGISTRADA.' if nota_interna else texto,
            interno=nota_interna,
        )
        return mensagem

    @classmethod
    @transaction.atomic
    def alterar_status(cls, chamado, usuario, status, resolucao=''):
        chamado = Chamado.objects.select_for_update().get(pk=chamado.pk)
        if status not in cls.status_permitidos(chamado, usuario):
            raise PermissionDenied('TRANSIÇÃO DE STATUS NÃO AUTORIZADA.')
        status_anterior = chamado.status
        chamado.status = status
        agora = timezone.now()
        if status == Chamado.Status.EM_ATENDIMENTO:
            chamado.iniciado_em = chamado.iniciado_em or agora
            chamado.resolvido_em = None
            chamado.fechado_em = None
        if status == Chamado.Status.RESOLVIDO:
            chamado.resolvido_em = agora
            chamado.resolucao = resolucao
        elif status == Chamado.Status.FECHADO:
            chamado.fechado_em = agora
            chamado.resolucao = resolucao or chamado.resolucao
        elif resolucao:
            chamado.resolucao = resolucao
        chamado.full_clean()
        chamado.save()
        cls._evento(
            chamado,
            'STATUS',
            f'STATUS ALTERADO DE {status_anterior} PARA {status}.',
            usuario,
            {'status_anterior': status_anterior, 'status_novo': status},
        )
        cls._comunicar(
            chamado,
            usuario,
            f'CHAMADO {chamado.protocolo}: {chamado.get_status_display()}',
            chamado.resolucao or f'STATUS ALTERADO PARA {chamado.get_status_display()}.',
            tipo='URGENTE' if status == Chamado.Status.CANCELADO else 'OPERACIONAL',
        )
        return chamado
