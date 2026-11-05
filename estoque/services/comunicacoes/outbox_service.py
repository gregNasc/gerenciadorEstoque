from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from estoque.models import ComunicadoEntrega
from integracao.scopes import IntegrationExecutionScope, IntegrationScopeError

from .phone import normalizar_whatsapp
from .providers import DisabledWhatsAppProvider, obter_provedor
from .providers.base import ProviderResult
from .providers.email import DisabledEmailProvider, obter_provedor_email
from .templates import TemplatePayloadError, construir_payload


class OutboxService:
    @classmethod
    def processar(cls, *, canal=ComunicadoEntrega.Canal.WHATSAPP, limit=100):
        if canal not in (
            ComunicadoEntrega.Canal.EMAIL,
            ComunicadoEntrega.Canal.WHATSAPP,
        ):
            raise ValueError('Somente canais externos podem ser processados pela outbox.')
        agora = timezone.now()
        configuracao = cls._configuracao(canal)
        with transaction.atomic():
            limite_travado = agora - timedelta(
                seconds=configuracao['processing_timeout']
            )
            ComunicadoEntrega.objects.filter(
                canal=canal,
                status=ComunicadoEntrega.Status.PROCESSANDO,
                processada_em__lte=limite_travado,
            ).update(
                status=ComunicadoEntrega.Status.FALHA,
                proxima_tentativa_em=agora,
                ultimo_erro='PROCESSAMENTO ANTERIOR EXPIROU E FOI REAGENDADO.',
            )
            entregas = list(
                ComunicadoEntrega.objects.select_related(
                    'comunicado__criado_por', 'usuario__perfil'
                ).select_for_update(skip_locked=True).filter(
                    canal=canal,
                    status__in=[ComunicadoEntrega.Status.PENDENTE, ComunicadoEntrega.Status.FALHA],
                ).filter(
                    Q(proxima_tentativa_em__isnull=True) | Q(proxima_tentativa_em__lte=agora)
                ).order_by('criada_em')[:limit]
            )
            for entrega in entregas:
                entrega.status = ComunicadoEntrega.Status.PROCESSANDO
                entrega.processada_em = agora
            ComunicadoEntrega.objects.bulk_update(entregas, ['status', 'processada_em'])

        provedor = cls._obter_provedor(canal)
        processadas = []
        for entrega in entregas:
            motivo_bloqueio = cls._validar_destinatario(entrega)
            if motivo_bloqueio:
                cls._marcar_ignorada(entrega.pk, motivo_bloqueio)
                processadas.append(entrega.pk)
                continue
            if isinstance(
                provedor, (DisabledWhatsAppProvider, DisabledEmailProvider)
            ):
                cls._marcar_ignorada(
                    entrega.pk,
                    f'Provedor de {canal.lower()} desabilitado.',
                )
                processadas.append(entrega.pk)
                continue
            try:
                integration_scope = cls._integration_scope(entrega)
                payload = cls._construir_payload(entrega)
                resultado = provedor.enviar_payload(
                    destino=entrega.destino,
                    payload=payload,
                    idempotency_key=str(entrega.idempotency_key),
                    execution_scope=integration_scope,
                )
            except (TemplatePayloadError, IntegrationScopeError) as exc:
                resultado = ProviderResult(sucesso=False, erro=str(exc), repetivel=False)
            except Exception:
                resultado = ProviderResult(
                    sucesso=False,
                    erro='ERRO INTERNO ISOLADO AO PROCESSAR A ENTREGA.',
                    repetivel=True,
                )
            cls._persistir_resultado(
                entrega.pk,
                resultado,
                max_retries=configuracao['max_retries'],
                retry_base=configuracao['retry_base'],
            )
            processadas.append(entrega.pk)
        return processadas

    @staticmethod
    def _configuracao(canal):
        if canal == ComunicadoEntrega.Canal.EMAIL:
            return {
                'max_retries': settings.NOTIFICACOES_EMAIL_MAX_RETRIES,
                'retry_base': settings.NOTIFICACOES_EMAIL_RETRY_BASE_SECONDS,
                'processing_timeout': (
                    settings.NOTIFICACOES_EMAIL_PROCESSING_TIMEOUT_SECONDS
                ),
            }
        return {
            'max_retries': settings.WHATSAPP_MAX_RETRIES,
            'retry_base': settings.WHATSAPP_RETRY_BASE_SECONDS,
            'processing_timeout': settings.WHATSAPP_PROCESSING_TIMEOUT_SECONDS,
        }

    @staticmethod
    def _obter_provedor(canal):
        if canal == ComunicadoEntrega.Canal.EMAIL:
            return obter_provedor_email()
        return obter_provedor()

    @staticmethod
    def _construir_payload(entrega):
        if entrega.canal == ComunicadoEntrega.Canal.EMAIL:
            parametros = entrega.parametros
            corpo = (parametros.get('mensagem') or '').strip()
            caminho = (parametros.get('url') or '').strip()
            if caminho:
                url = urljoin(
                    f"{settings.APP_BASE_URL.rstrip('/')}/",
                    caminho.lstrip('/'),
                )
                corpo = f'{corpo}\n\nAcessar no sistema: {url}'.strip()
            return {
                'assunto': (parametros.get('titulo') or 'Notificação').strip(),
                'corpo': corpo or 'Há uma nova notificação no sistema.',
            }
        return construir_payload(
            template_codigo=entrega.template_codigo,
            idioma=entrega.parametros.get('idioma'),
            parametros=entrega.parametros,
        )

    @staticmethod
    def _validar_destinatario(entrega):
        usuario = entrega.usuario
        if not usuario.is_active:
            return 'DESTINATÁRIO INATIVO; ENTREGA CANCELADA.'

        dados = entrega.comunicado.dados or {}
        if dados.get('conteudo_financeiro'):
            from estoque.policies.compras import ComprasAccessPolicy

            if not ComprasAccessPolicy.pode_visualizar_valores(usuario):
                return 'CONTEÚDO FINANCEIRO NÃO AUTORIZADO PARA O DESTINATÁRIO.'

        if entrega.canal == ComunicadoEntrega.Canal.EMAIL:
            email_atual = (usuario.email or '').strip().lower()
            try:
                validate_email(email_atual)
            except ValidationError:
                return 'ENDEREÇO DE E-MAIL INVÁLIDO OU AUSENTE.'
            if email_atual != (entrega.destino or '').strip().lower():
                return 'ENDEREÇO DE E-MAIL ALTERADO; GERE UMA NOVA ENTREGA.'
            return ''

        try:
            perfil = usuario.perfil
        except ObjectDoesNotExist:
            return 'PERFIL DO DESTINATÁRIO NÃO ENCONTRADO.'
        if (
            not perfil.whatsapp_ativo
            or not perfil.whatsapp_consentimento_em
            or perfil.whatsapp_revogado_em
        ):
            return 'CONSENTIMENTO DE WHATSAPP AUSENTE OU REVOGADO.'
        if normalizar_whatsapp(perfil.whatsapp_numero) != entrega.destino:
            return 'NÚMERO DE WHATSAPP ALTERADO; GERE UMA NOVA ENTREGA.'
        return ''

    @staticmethod
    def _integration_scope(entrega):
        declared = entrega.parametros.get('_integration_scope') or {}
        kind = declared.get('kind')
        source = declared.get('source') or (
            'EMAIL_COMUNICADOS'
            if entrega.canal == ComunicadoEntrega.Canal.EMAIL
            else 'WHATSAPP_COMUNICADOS'
        )
        company_id = declared.get('company_id')
        if kind:
            return IntegrationExecutionScope(
                kind=kind,
                source=source,
                company_id=company_id,
            )
        comunicado = entrega.comunicado
        if comunicado.empresa_id:
            return IntegrationExecutionScope.tenant(source, comunicado.empresa_id)
        if comunicado.criado_por.is_superuser:
            return IntegrationExecutionScope.platform_global(source)
        raise IntegrationScopeError(
            'Entrega externa sem empresa ou escopo global autorizado.'
        )

    @staticmethod
    def _marcar_ignorada(entrega_id, motivo):
        ComunicadoEntrega.objects.filter(pk=entrega_id).update(
            status=ComunicadoEntrega.Status.IGNORADA,
            ultimo_erro=motivo,
            processada_em=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def _persistir_resultado(
        entrega_id, resultado, *, max_retries=None, retry_base=None,
    ):
        entrega = ComunicadoEntrega.objects.select_for_update().get(pk=entrega_id)
        if entrega.status in (
            ComunicadoEntrega.Status.ENVIADA,
            ComunicadoEntrega.Status.ENTREGUE,
            ComunicadoEntrega.Status.LIDA,
        ):
            return entrega
        agora = timezone.now()
        entrega.tentativas += 1
        entrega.processada_em = agora
        if resultado.sucesso:
            entrega.status = ComunicadoEntrega.Status.ENVIADA
            entrega.provider_message_id = resultado.provider_message_id
            entrega.enviada_em = agora
            entrega.ultimo_erro = ''
            entrega.provider_resposta = resultado.resposta
            entrega.proxima_tentativa_em = None
        else:
            entrega.ultimo_erro = resultado.erro[:4000]
            entrega.provider_resposta = resultado.resposta
            limite = max_retries or settings.WHATSAPP_MAX_RETRIES
            if resultado.repetivel and entrega.tentativas < limite:
                entrega.status = ComunicadoEntrega.Status.FALHA
                base = retry_base or settings.WHATSAPP_RETRY_BASE_SECONDS
                espera = base * (2 ** (entrega.tentativas - 1))
                entrega.proxima_tentativa_em = agora + timedelta(seconds=espera)
            else:
                entrega.status = ComunicadoEntrega.Status.FALHA
                entrega.proxima_tentativa_em = None
        entrega.save(update_fields=[
            'status', 'tentativas', 'processada_em', 'provider_message_id',
            'provider_resposta', 'enviada_em', 'ultimo_erro', 'proxima_tentativa_em',
        ])
        return entrega

