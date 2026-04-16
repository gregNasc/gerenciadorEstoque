from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Perfil


@receiver(post_save, sender=User)
def criar_perfil(sender, instance, created, **kwargs):
    if created:
        Perfil.objects.create(
            user=instance,
            role='operador'
        )

def validar_regionais(sender, instance, action, pk_set, **kwargs):
    if action == "pre_add":
        bases = Base.objects.filter(pk__in=pk_set)
        for base in bases:
            if base.empresa != instance.empresa:
                raise ValidationError("Base não pertence à empresa do perfil")

