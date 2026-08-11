from django.db.models import Q

from compras.models import Aquisicao, RemessaCompra
from estoque.policies.compras import ComprasAccessPolicy


class AquisicaoAccessPolicy:
    @classmethod
    def queryset(cls, user):
        if not ComprasAccessPolicy.pode_visualizar_valores(user):
            return Aquisicao.objects.none()
        perfil = getattr(user, 'perfil', None)
        if user.is_superuser or (perfil and perfil.is_admin):
            return Aquisicao.objects.all()
        return Aquisicao.objects.filter(empresa__in=ComprasAccessPolicy.empresas(user))

    @classmethod
    def remessas(cls, user):
        if not user or not user.is_authenticated or ComprasAccessPolicy.restrito(user):
            return RemessaCompra.objects.none()
        perfil = getattr(user, 'perfil', None)
        if user.is_superuser or (perfil and perfil.is_admin):
            return RemessaCompra.objects.all()
        bases_operacionais = perfil.regionais.all()
        bases_compras = ComprasAccessPolicy.bases(user)
        return RemessaCompra.objects.filter(
            Q(base_destino__in=bases_operacionais)
            | Q(base_origem__in=bases_operacionais)
            | Q(base_destino__in=bases_compras)
            | Q(base_origem__in=bases_compras)
        ).distinct()

    @staticmethod
    def pode_gerenciar(user):
        return ComprasAccessPolicy.pode_gerenciar_catalogo(user) or (
            user.is_authenticated
            and not ComprasAccessPolicy.restrito(user)
            and user.has_perm('compras.gerenciar_aquisicoes')
        )

    @staticmethod
    def pode_confirmar(user, remessa):
        if not user or not user.is_authenticated or ComprasAccessPolicy.restrito(user):
            return False
        perfil = getattr(user, 'perfil', None)
        return bool(
            user.is_superuser
            or (perfil and perfil.is_admin)
            or user.has_perm('compras.confirmar_remessa_compra')
            or (
                perfil
                and (perfil.is_gestor or perfil.is_operador)
                and perfil.regionais.filter(pk=remessa.base_destino_id).exists()
            )
        )
