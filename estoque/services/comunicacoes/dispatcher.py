from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from estoque.models import Comunicado, ComunicadoEntrega
from integracao.scopes import IntegrationExecutionScope

from .phone import normalizar_whatsapp, whatsapp_valido
from .templates import codigo_template


class ComunicacaoDispatcher:
    normalizar_whatsapp = staticmethod(normalizar_whatsapp)

    @staticmethod
    def _integration_scope(comunicado):
        if comunicado.empresa_id:
            return IntegrationExecutionScope.tenant(
                'WHATSAPP_COMUNICADOS', comunicado.empresa_id
            )
        if comunicado.criado_por.is_superuser:
            return IntegrationExecutionScope.platform_global(
                'WHATSAPP_COMUNICADOS'
            )
        return None

    @classmethod
    @transaction.atomic
    def criar_entregas(cls, comunicado_id):
        comunicado = Comunicado.objects.select_related(
            'empresa', 'criado_por'
        ).prefetch_related('usuarios__perfil').get(pk=comunicado_id)
        integration_scope = cls._integration_scope(comunicado)
        criadas = []
        for usuario in comunicado.usuarios.filter(is_active=True):
            entrega, _ = ComunicadoEntrega.objects.get_or_create(
                comunicado=comunicado,
                usuario=usuario,
                canal=ComunicadoEntrega.Canal.SISTEMA,
                defaults={
                    'status': ComunicadoEntrega.Status.ENTREGUE,
                    'destino': usuario.get_username(),
                },
            )
            criadas.append(entrega)
            if not settings.WHATSAPP_ENABLED:
                continue
            try:
                perfil = usuario.perfil
            except ObjectDoesNotExist:
                perfil = None
            if (
                not perfil
                or not perfil.whatsapp_ativo
                or not perfil.whatsapp_consentimento_em
                or perfil.whatsapp_revogado_em
            ):
                continue
            destino = cls.normalizar_whatsapp(perfil.whatsapp_numero)
            valido = whatsapp_valido(destino)
            template = codigo_template(comunicado)
            erro = ''
            if not valido:
                erro = 'NÚMERO DE WHATSAPP INVÁLIDO.'
            elif not template:
                erro = 'TEMPLATE DE WHATSAPP NÃO CADASTRADO.'
            elif integration_scope is None:
                erro = 'ESCOPO DE TENANT DA INTEGRAÇÃO NÃO DECLARADO.'
            entrega, _ = ComunicadoEntrega.objects.get_or_create(
                comunicado=comunicado,
                usuario=usuario,
                canal=ComunicadoEntrega.Canal.WHATSAPP,
                defaults={
                    'status': (
                        ComunicadoEntrega.Status.PENDENTE
                        if valido and template and integration_scope
                        else ComunicadoEntrega.Status.IGNORADA
                    ),
                    'destino': destino,
                    'provedor': settings.WHATSAPP_PROVIDER,
                    'template_codigo': template or '',
                    'parametros': {
                        'titulo': comunicado.titulo,
                        'mensagem': comunicado.mensagem,
                        'url': comunicado.url,
                        'idioma': perfil.idioma,
                        '_integration_scope': (
                            integration_scope.as_dict()
                            if integration_scope else {}
                        ),
                    },
                    'ultimo_erro': erro,
                },
            )
            criadas.append(entrega)
        return criadas
