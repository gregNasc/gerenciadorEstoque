from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from chamados.models import (
    AliasUsuario,
    InventarioLiderHistorico,
    PendenciaVinculoLider,
    normalizar_alias,
)
from chamados.policies import ChamadoAccessPolicy
from insumos.models import Inventario


class InventarioLiderService:
    @staticmethod
    def inventarios_do_dia(usuario, data=None):
        data = data or timezone.localdate()
        return Inventario.objects.filter(
            lider_usuario=usuario,
            data_inicio__lte=data,
        ).filter(
            Q(data_fim__isnull=True) | Q(data_fim__gte=data)
        ).select_related('cliente', 'base').order_by('inicio_previsto', 'loja')

    @classmethod
    @transaction.atomic
    def resolver_texto_importado(cls, inventario, usuario_sistema):
        inventario = Inventario.objects.select_for_update().get(pk=inventario.pk)
        texto = (inventario.lider or '').strip()
        normalizado = normalizar_alias(texto)
        alias = AliasUsuario.objects.filter(
            alias_normalizado=normalizado, ativo=True,
        ).select_related('usuario').first() if normalizado else None
        if alias:
            cls._vincular_locked(
                inventario, alias.usuario, usuario_sistema,
                'VÍNCULO AUTOMÁTICO POR ALIAS ADMINISTRATIVO.',
            )
            PendenciaVinculoLider.objects.filter(inventario=inventario).update(
                status=PendenciaVinculoLider.Status.RESOLVIDA,
                resolvida_por=usuario_sistema,
                resolvida_em=timezone.now(),
                justificativa='RESOLVIDA AUTOMATICAMENTE POR ALIAS.',
            )
            return alias.usuario
        PendenciaVinculoLider.objects.update_or_create(
            inventario=inventario,
            defaults={
                'texto_importado': texto or 'NÃO INFORMADO',
                'texto_normalizado': normalizado,
                'status': PendenciaVinculoLider.Status.PENDENTE,
                'resolvida_por': None,
                'resolvida_em': None,
                'justificativa': '',
            },
        )
        return None

    @staticmethod
    def _vincular_locked(inventario, lider_novo, autor, justificativa):
        anterior = inventario.lider_usuario
        if anterior == lider_novo:
            return inventario
        InventarioLiderHistorico.objects.create(
            inventario=inventario,
            lider_anterior=anterior,
            lider_novo=lider_novo,
            texto_original=inventario.lider or '',
            justificativa=justificativa,
            alterado_por=autor,
        )
        inventario.lider_usuario = lider_novo
        inventario.save(update_fields=['lider_usuario'])
        return inventario

    @classmethod
    @transaction.atomic
    def vincular(cls, inventario, lider_novo, autor, justificativa):
        if not ChamadoAccessPolicy.pode_configurar(autor):
            raise PermissionDenied('SEM PERMISSÃO PARA VINCULAR LÍDERES.')
        if not (justificativa or '').strip():
            raise ValidationError('INFORME A JUSTIFICATIVA DA SUBSTITUIÇÃO DO LÍDER.')
        inventario = Inventario.objects.select_for_update().get(pk=inventario.pk)
        cls._vincular_locked(inventario, lider_novo, autor, justificativa)
        PendenciaVinculoLider.objects.filter(inventario=inventario).update(
            status=PendenciaVinculoLider.Status.RESOLVIDA,
            resolvida_por=autor,
            resolvida_em=timezone.now(),
            justificativa=justificativa,
        )
        return inventario

    @staticmethod
    @transaction.atomic
    def cadastrar_alias(*, usuario, alias, autor):
        if not ChamadoAccessPolicy.pode_configurar(autor):
            raise PermissionDenied('SEM PERMISSÃO PARA CADASTRAR ALIASES.')
        normalizado = normalizar_alias(alias)
        if not normalizado:
            raise ValidationError('INFORME UM ALIAS VÁLIDO.')
        registro = AliasUsuario(
            usuario=usuario, alias=alias, alias_normalizado=normalizado,
        )
        registro.full_clean()
        registro.save()
        return registro
