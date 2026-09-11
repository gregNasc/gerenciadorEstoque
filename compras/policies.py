from django.db.models import Q

from compras.models import Aquisicao, RemessaCompra
from estoque.models import Base, Empresa
from estoque.policies.compras import ComprasAccessPolicy


class AquisicaoAccessPolicy:
    @classmethod
    def queryset(cls, user, *, action=ComprasAccessPolicy.VIEW):
        if action in {
            ComprasAccessPolicy.CREATE,
            ComprasAccessPolicy.EDIT,
            ComprasAccessPolicy.APPROVE,
            ComprasAccessPolicy.ADMIN,
        }:
            permitido = cls.pode_gerenciar(user)
        else:
            permitido = ComprasAccessPolicy.pode_visualizar_valores(user)
        if not permitido:
            return Aquisicao.objects.none()
        return Aquisicao.objects.filter(
            empresa__in=ComprasAccessPolicy.empresas(user, action=action)
        )

    @classmethod
    def remessas(cls, user, *, action=ComprasAccessPolicy.VIEW):
        if not user or not user.is_authenticated or ComprasAccessPolicy.restrito(user):
            return RemessaCompra.objects.none()
        if user.is_superuser:
            return RemessaCompra.objects.all()
        perfil = getattr(user, 'perfil', None)
        if not perfil:
            return RemessaCompra.objects.none()
        bases_ids = set(
            ComprasAccessPolicy.bases(user, action=action).values_list('pk', flat=True)
        )
        empresas_ids = set(
            ComprasAccessPolicy.empresas(user, action=action).values_list('pk', flat=True)
        )
        if perfil.role in {perfil.Role.GESTOR, perfil.Role.OPERADOR}:
            bases_ids.update(perfil.regionais.values_list('pk', flat=True))
            if perfil.empresa_id:
                empresas_ids.add(perfil.empresa_id)
        bases_compras = Base.objects.filter(pk__in=bases_ids)
        empresas = Empresa.objects.filter(pk__in=empresas_ids)
        return RemessaCompra.objects.filter(
            Q(empresa__in=empresas)
            & (
                Q(base_destino__in=bases_compras)
                | Q(base_origem__in=bases_compras)
            )
        ).distinct()

    @staticmethod
    def pode_gerenciar(user):
        return ComprasAccessPolicy.pode_gerenciar_catalogo(user) or (
            user.is_authenticated
            and not ComprasAccessPolicy.restrito(user)
            and user.has_perm('compras.gerenciar_aquisicoes')
        )

    @classmethod
    def pode_confirmar(cls, user, remessa):
        if not user or not user.is_authenticated or ComprasAccessPolicy.restrito(user):
            return False
        perfil = getattr(user, 'perfil', None)
        return bool(
            cls.remessas(
                user,
                action=ComprasAccessPolicy.APPROVE,
            ).filter(pk=remessa.pk).exists()
            and (
                user.is_superuser
                or (perfil and perfil.is_admin)
                or user.has_perm('compras.confirmar_remessa_compra')
                or (
                    perfil
                    and (perfil.is_gestor or perfil.is_operador)
                    and perfil.regionais.filter(pk=remessa.base_destino_id).exists()
                )
            )
        )
