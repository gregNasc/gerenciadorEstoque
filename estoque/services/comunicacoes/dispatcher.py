from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import validate_email
from django.db import transaction

from estoque.models import Comunicado, ComunicadoEntrega
from integracao.scopes import IntegrationExecutionScope

from .phone import normalizar_whatsapp, whatsapp_valido
from .templates import codigo_template


class ComunicacaoDispatcher:
    normalizar_whatsapp = staticmethod(normalizar_whatsapp)

    @staticmethod
    def _integration_scope(comunicado, source):
        if comunicado.empresa_id:
            return IntegrationExecutionScope.tenant(
                source, comunicado.empresa_id
            )
        if comunicado.criado_por.is_superuser:
            return IntegrationExecutionScope.platform_global(
                source
            )
        return None

    @staticmethod
    def _email_valido(email):
        try:
            validate_email(email)
        except ValidationError:
            return False
        return True

    @staticmethod
    def _pode_receber_conteudo(comunicado, usuario):
        from estoque.policies.comunicacoes import (
            RestricaoComunicacaoUsuarioPolicy,
        )

        if not RestricaoComunicacaoUsuarioPolicy.pode_receber(
            comunicado, usuario,
        ):
            return False
        dados = comunicado.dados or {}
        if not dados.get('conteudo_financeiro'):
            return True
        from estoque.policies.compras import ComprasAccessPolicy

        return ComprasAccessPolicy.pode_visualizar_valores(usuario)

    @classmethod
    @transaction.atomic
    def criar_entregas(cls, comunicado_id):
        comunicado = Comunicado.objects.select_related(
            'empresa', 'criado_por'
        ).prefetch_related('usuarios__perfil').get(pk=comunicado_id)
        whatsapp_scope = cls._integration_scope(
            comunicado, 'WHATSAPP_COMUNICADOS'
        )
        email_scope = cls._integration_scope(
            comunicado, 'EMAIL_COMUNICADOS'
        )
        criadas = []
        for usuario in comunicado.usuarios.filter(is_active=True):
            if not cls._pode_receber_conteudo(comunicado, usuario):
                # Fail-closed também para o canal interno: a associação M2M é
                # a autorização usada pela Central de Comunicados.
                comunicado.usuarios.remove(usuario)
                continue
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

            if settings.NOTIFICACOES_EMAIL_ENABLED:
                destino_email = (usuario.email or '').strip().lower()
                email_valido = cls._email_valido(destino_email)
                erro_email = ''
                if not email_valido:
                    erro_email = 'ENDEREÇO DE E-MAIL INVÁLIDO OU AUSENTE.'
                elif email_scope is None:
                    erro_email = 'ESCOPO DA INTEGRAÇÃO DE E-MAIL NÃO DECLARADO.'
                entrega_email, _ = ComunicadoEntrega.objects.get_or_create(
                    comunicado=comunicado,
                    usuario=usuario,
                    canal=ComunicadoEntrega.Canal.EMAIL,
                    defaults={
                        'status': (
                            ComunicadoEntrega.Status.PENDENTE
                            if not erro_email
                            else ComunicadoEntrega.Status.IGNORADA
                        ),
                        'destino': destino_email,
                        'provedor': 'django-email',
                        'parametros': {
                            'titulo': comunicado.titulo,
                            'mensagem': comunicado.mensagem,
                            'url': comunicado.url,
                            '_integration_scope': (
                                email_scope.as_dict() if email_scope else {}
                            ),
                        },
                        'ultimo_erro': erro_email,
                    },
                )
                criadas.append(entrega_email)

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
            elif whatsapp_scope is None:
                erro = 'ESCOPO DA INTEGRAÇÃO DE WHATSAPP NÃO DECLARADO.'
            entrega, _ = ComunicadoEntrega.objects.get_or_create(
                comunicado=comunicado,
                usuario=usuario,
                canal=ComunicadoEntrega.Canal.WHATSAPP,
                defaults={
                    'status': (
                        ComunicadoEntrega.Status.PENDENTE
                        if not erro
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
                            whatsapp_scope.as_dict()
                            if whatsapp_scope else {}
                        ),
                    },
                    'ultimo_erro': erro,
                },
            )
            criadas.append(entrega)
        return criadas
