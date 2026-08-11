from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from estoque.models import ComunicadoEntrega, Perfil

from .phone import normalizar_whatsapp, whatsapp_valido


class WhatsAppConsentimentoService:
    @staticmethod
    @transaction.atomic
    def ativar(perfil, *, numero, origem):
        perfil = Perfil.objects.select_for_update().get(pk=perfil.pk)
        numero = normalizar_whatsapp(numero)
        origem = (origem or '').strip().upper()
        if not whatsapp_valido(numero):
            raise ValidationError('INFORME UM NÚMERO DE WHATSAPP INTERNACIONAL VÁLIDO.')
        if not origem:
            raise ValidationError('INFORME A ORIGEM DO CONSENTIMENTO.')
        perfil.whatsapp_numero = numero
        perfil.whatsapp_ativo = True
        perfil.whatsapp_consentimento_em = timezone.now()
        perfil.whatsapp_consentimento_origem = origem
        perfil.whatsapp_revogado_em = None
        perfil.save(update_fields=[
            'whatsapp_numero',
            'whatsapp_ativo',
            'whatsapp_consentimento_em',
            'whatsapp_consentimento_origem',
            'whatsapp_revogado_em',
        ])
        return perfil

    @staticmethod
    @transaction.atomic
    def revogar(perfil):
        perfil = Perfil.objects.select_for_update().get(pk=perfil.pk)
        perfil.whatsapp_ativo = False
        perfil.whatsapp_revogado_em = timezone.now()
        perfil.save(update_fields=['whatsapp_ativo', 'whatsapp_revogado_em'])
        ComunicadoEntrega.objects.filter(
            usuario=perfil.user,
            canal=ComunicadoEntrega.Canal.WHATSAPP,
            status__in=[
                ComunicadoEntrega.Status.PENDENTE,
                ComunicadoEntrega.Status.PROCESSANDO,
                ComunicadoEntrega.Status.FALHA,
            ],
        ).update(
            status=ComunicadoEntrega.Status.CANCELADA,
            proxima_tentativa_em=None,
            ultimo_erro='CONSENTIMENTO REVOGADO PELO USUÁRIO.',
        )
        return perfil
