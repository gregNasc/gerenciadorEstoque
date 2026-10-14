import hashlib

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from estoque.models import (
    Comunicado,
    ComunicadoEntrega,
    EntregaNotificacaoCustodia,
    EventoNotificacaoCustodia,
    Perfil,
)
from estoque.services.comunicacoes.phone import (
    normalizar_whatsapp,
    whatsapp_valido,
)


class CustodiaNotificacaoService:
    EVENT_CONTENT = {
        EventoNotificacaoCustodia.Evento.CUSTODIA_CRIADA: (
            'Custódia registrada',
            'Uma Custódia de ativos foi registrada para {colaborador}.',
            'custodia_criada',
        ),
        EventoNotificacaoCustodia.Evento.TERMO_GERADO: (
            'Termo de Custódia gerado',
            'O termo de {tipo_termo} da Custódia de {colaborador} foi gerado.',
            'custodia_termo_gerado',
        ),
        EventoNotificacaoCustodia.Evento.TERMO_ENVIADO: (
            'Termo enviado para assinatura',
            'O termo da Custódia de {colaborador} foi enviado para assinatura.',
            'custodia_termo_enviado',
        ),
        EventoNotificacaoCustodia.Evento.TERMO_ASSINADO: (
            'Termo parcialmente assinado',
            'O termo da Custódia de {colaborador} recebeu uma assinatura.',
            'custodia_termo_assinado',
        ),
        EventoNotificacaoCustodia.Evento.TERMO_CONCLUIDO: (
            'Termo de Custódia concluído',
            'O termo da Custódia de {colaborador} foi concluído e arquivado.',
            'custodia_termo_concluido',
        ),
        EventoNotificacaoCustodia.Evento.DEVOLUCAO_REGISTRADA: (
            'Devolução de Custódia registrada',
            'Uma devolução de ativos de {colaborador} foi registrada.',
            'custodia_devolucao_registrada',
        ),
    }
    RH_EVENTS = {
        EventoNotificacaoCustodia.Evento.TERMO_ENVIADO,
        EventoNotificacaoCustodia.Evento.TERMO_ASSINADO,
        EventoNotificacaoCustodia.Evento.TERMO_CONCLUIDO,
    }

    @classmethod
    @transaction.atomic
    def publicar(
        cls,
        *,
        evento,
        custodia,
        criado_por,
        termo_entrega=None,
        termo_devolucao=None,
        devolucao=None,
        envelope_docusign=None,
    ):
        if evento not in EventoNotificacaoCustodia.Evento.values:
            raise ValueError('Evento de Custódia não suportado.')
        if not criado_por or not criado_por.is_active:
            raise ValueError('O usuário responsável deve estar ativo.')
        event_key = cls._event_key(
            evento=evento,
            custodia=custodia,
            termo_entrega=termo_entrega,
            termo_devolucao=termo_devolucao,
            devolucao=devolucao,
            envelope_docusign=envelope_docusign,
        )
        tipo_termo = 'entrega' if termo_entrega else 'devolução'
        title_template, message_template, template_code = cls.EVENT_CONTENT[evento]
        context = {
            'colaborador': custodia.colaborador.nome,
            'tipo_termo': tipo_termo,
        }
        defaults = {
            'empresa': custodia.empresa,
            'custodia': custodia,
            'devolucao': devolucao,
            'termo_entrega': termo_entrega,
            'termo_devolucao': termo_devolucao,
            'envelope_docusign': envelope_docusign,
            'evento': evento,
            'titulo': title_template.format(**context),
            'mensagem': message_template.format(**context),
            'link': '/',
            'dados': {
                'schema_version': 1,
                'evento': evento,
                'custodia_id': custodia.pk,
                'empresa_id': custodia.empresa_id,
                'template_codigo': template_code,
            },
            'criado_por': criado_por,
        }
        notification, _created = EventoNotificacaoCustodia.objects.get_or_create(
            event_key=event_key,
            defaults=defaults,
        )
        cls._ensure_internal(notification)
        cls._ensure_external(notification, template_code=template_code)
        notification.refresh_from_db()
        return notification

    @staticmethod
    def _event_key(**context):
        evento = context['evento']
        target = (
            context.get('envelope_docusign')
            or context.get('termo_devolucao')
            or context.get('termo_entrega')
            or context.get('devolucao')
            or context['custodia']
        )
        return f'{evento}:{target._meta.label_lower}:{target.pk}'

    @classmethod
    def _ensure_internal(cls, notification):
        collaborator = notification.custodia.colaborador
        user = collaborator.usuario
        if not user or not user.is_active:
            return
        if not notification.comunicado_id:
            communication = Comunicado.objects.create(
                titulo=notification.titulo,
                mensagem=notification.mensagem,
                tipo='OPERACIONAL',
                criado_por=notification.criado_por,
                empresa=notification.empresa,
                enviar_para_todos=False,
                dados={
                    'evento_custodia': notification.evento,
                    'event_key': notification.event_key,
                },
                url=notification.link,
            )
            communication.usuarios.add(user)
            EventoNotificacaoCustodia.objects.filter(pk=notification.pk).update(
                comunicado=communication,
            )
            notification.comunicado = communication
        ComunicadoEntrega.objects.get_or_create(
            comunicado=notification.comunicado,
            usuario=user,
            canal=ComunicadoEntrega.Canal.SISTEMA,
            defaults={
                'status': ComunicadoEntrega.Status.ENTREGUE,
                'destino': user.get_username(),
            },
        )
        cls._delivery(
            notification=notification,
            channel=EntregaNotificacaoCustodia.Canal.SISTEMA,
            name=collaborator.nome,
            destination=user.get_username(),
            status=EntregaNotificacaoCustodia.Status.ENTREGUE,
            user=user,
            collaborator=collaborator,
            provider='GERENCIADOR',
        )

    @classmethod
    def _ensure_external(cls, notification, *, template_code):
        collaborator = notification.custodia.colaborador
        if collaborator.email:
            cls._delivery(
                notification=notification,
                channel=EntregaNotificacaoCustodia.Canal.EMAIL,
                name=collaborator.nome,
                destination=collaborator.email,
                status=(
                    EntregaNotificacaoCustodia.Status.PENDENTE
                    if settings.CUSTODIA_EMAIL_ENABLED
                    else EntregaNotificacaoCustodia.Status.IGNORADA
                ),
                user=collaborator.usuario,
                collaborator=collaborator,
                provider=settings.EMAIL_BACKEND,
                error=(
                    '' if settings.CUSTODIA_EMAIL_ENABLED
                    else 'Canal de e-mail de Custódia desabilitado.'
                ),
            )
        if notification.evento in cls.RH_EVENTS:
            cls._ensure_rh_email(notification)
        cls._ensure_whatsapp(
            notification,
            collaborator=collaborator,
            template_code=template_code,
        )

    @classmethod
    def _ensure_rh_email(cls, notification):
        try:
            config = notification.empresa.configuracao_docusign
        except ObjectDoesNotExist:
            return
        if not config.email_testemunha_rh:
            return
        cls._delivery(
            notification=notification,
            channel=EntregaNotificacaoCustodia.Canal.EMAIL,
            name=config.nome_testemunha_rh,
            destination=config.email_testemunha_rh,
            status=(
                EntregaNotificacaoCustodia.Status.PENDENTE
                if settings.CUSTODIA_EMAIL_ENABLED
                else EntregaNotificacaoCustodia.Status.IGNORADA
            ),
            provider=settings.EMAIL_BACKEND,
            error=(
                '' if settings.CUSTODIA_EMAIL_ENABLED
                else 'Canal de e-mail de Custódia desabilitado.'
            ),
        )

    @classmethod
    def _ensure_whatsapp(cls, notification, *, collaborator, template_code):
        user = collaborator.usuario
        if not user or not user.is_active:
            return
        try:
            profile = user.perfil
        except Perfil.DoesNotExist:
            return
        if (
            not profile.whatsapp_ativo
            or not profile.whatsapp_consentimento_em
            or profile.whatsapp_revogado_em
        ):
            return
        destination = normalizar_whatsapp(profile.whatsapp_numero)
        valid = whatsapp_valido(destination)
        enabled = settings.WHATSAPP_ENABLED and valid
        error = ''
        if not settings.WHATSAPP_ENABLED:
            error = 'Canal WhatsApp desabilitado.'
        elif not valid:
            error = 'Número de WhatsApp inválido.'
        cls._delivery(
            notification=notification,
            channel=EntregaNotificacaoCustodia.Canal.WHATSAPP,
            name=collaborator.nome,
            destination=destination or 'invalido',
            status=(
                EntregaNotificacaoCustodia.Status.PENDENTE
                if enabled else EntregaNotificacaoCustodia.Status.IGNORADA
            ),
            user=user,
            collaborator=collaborator,
            provider=settings.WHATSAPP_PROVIDER,
            template_code=template_code,
            parameters={
                'titulo': notification.titulo,
                'mensagem': notification.mensagem,
                'url': notification.link,
                'idioma': profile.idioma,
                '_integration_scope': {
                    'kind': 'TENANT',
                    'source': 'WHATSAPP_CUSTODIA',
                    'company_id': notification.empresa_id,
                },
            },
            error=error,
        )

    @staticmethod
    def _delivery(
        *, notification, channel, name, destination, status,
        user=None, collaborator=None, provider='', template_code='',
        parameters=None, error='',
    ):
        normalized_destination = (destination or '').strip().lower()
        key_source = (
            f'{notification.event_key}|{channel}|{normalized_destination}'
        )
        key = hashlib.sha256(key_source.encode()).hexdigest()
        delivery, _created = EntregaNotificacaoCustodia.objects.get_or_create(
            notificacao=notification,
            canal=channel,
            destino=normalized_destination,
            defaults={
                'usuario': user,
                'colaborador': collaborator,
                'status': status,
                'destinatario_nome': name,
                'provedor': provider,
                'template_codigo': template_code,
                'parametros': parameters or {},
                'idempotency_key': key,
                'ultimo_erro': error,
            },
        )
        return delivery
