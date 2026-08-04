import re

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from estoque.models import Comunicado, ComunicadoEntrega

from .templates import codigo_template


class ComunicacaoDispatcher:
    @staticmethod
    def normalizar_whatsapp(numero):
        digitos = re.sub(r'\D', '', numero or '')
        if digitos and len(digitos) in (10, 11):
            digitos = f'{settings.WHATSAPP_DEFAULT_COUNTRY_CODE}{digitos}'
        return digitos

    @classmethod
    @transaction.atomic
    def criar_entregas(cls, comunicado_id):
        comunicado = Comunicado.objects.prefetch_related('usuarios__perfil').get(pk=comunicado_id)
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
            if not perfil or not perfil.whatsapp_ativo or not perfil.whatsapp_consentimento_em:
                continue
            destino = cls.normalizar_whatsapp(perfil.whatsapp_numero)
            valido = 12 <= len(destino) <= 15
            entrega, _ = ComunicadoEntrega.objects.get_or_create(
                comunicado=comunicado,
                usuario=usuario,
                canal=ComunicadoEntrega.Canal.WHATSAPP,
                defaults={
                    'status': (
                        ComunicadoEntrega.Status.PENDENTE
                        if valido else ComunicadoEntrega.Status.IGNORADA
                    ),
                    'destino': destino,
                    'provedor': settings.WHATSAPP_PROVIDER,
                    'template_codigo': codigo_template(comunicado),
                    'parametros': {
                        'titulo': comunicado.titulo,
                        'mensagem': comunicado.mensagem,
                        'url': comunicado.url,
                        'idioma': perfil.idioma,
                    },
                    'ultimo_erro': '' if valido else 'Número de WhatsApp inválido.',
                },
            )
            criadas.append(entrega)
        return criadas
