from django.core.exceptions import ValidationError
from django.db import connections
from django.db.models.signals import m2m_changed, post_migrate, post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Base, Empresa, Perfil


@receiver(post_save, sender=User)
def criar_perfil(sender, instance, created, **kwargs):
    if created:
        Perfil.objects.create(
            user=instance,
            role='operador'
        )


@receiver(post_save, sender=Empresa)
def provisionar_modulos_empresa(
    sender,
    instance,
    created,
    raw=False,
    using='default',
    **kwargs,
):
    if created and not raw:
        from estoque.tenant_features import TenantFeatureService

        TenantFeatureService.ensure_catalog(using=using)
        # O onboarding cria o tenant inativo e, portanto, fail-closed. A criação
        # direta de um tenant já ativo é um caminho legado interno e preserva o
        # comportamento anterior para não interromper integrações existentes.
        TenantFeatureService.provision_defaults(
            instance,
            using=using,
            enabled=instance.ativa,
        )


@receiver(post_migrate, dispatch_uid='estoque.garantir_catalogo_modulos')
def garantir_catalogo_modulos(sender, using='default', **kwargs):
    if getattr(sender, 'label', None) != 'estoque':
        return
    from estoque.models import Modulo
    from estoque.tenant_features import TenantFeatureService

    if Modulo._meta.db_table not in connections[using].introspection.table_names():
        return
    TenantFeatureService.ensure_catalog(using=using)

@receiver(m2m_changed, sender=Perfil.regionais.through)
@receiver(m2m_changed, sender=Perfil.bases_checklist.through)
def validar_regionais(sender, instance, action, pk_set, reverse=False, **kwargs):
    if reverse:
        return
    if action == "pre_add":
        bases = Base.objects.filter(pk__in=pk_set)
        for base in bases:
            if not instance.empresa_id or base.empresa_id != instance.empresa_id:
                raise ValidationError("Base não pertence à empresa principal do perfil")

