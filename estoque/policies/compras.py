from django.contrib.auth.models import Group

from estoque.models import Base, Empresa
from insumos.constants import GruposInsumos


class GruposCorporativos:
    COMPRAS_RESTRITO = 'COMPRAS_RESTRITO_NOVAS_FUNCIONALIDADES'
    SICK_GERENCIAR = 'SICK_GERENCIAR'
    SICK_MANUTENCAO = 'SICK_MANUTENCAO'
    COMUNICADOS_EDITOR = 'COMUNICADOS_EDITOR'


class ComprasAccessPolicy:
    @staticmethod
    def _autenticado(user):
        return bool(user and user.is_authenticated)

    @classmethod
    def _pertence_ao_grupo(cls, user, nome):
        if not cls._autenticado(user):
            return False
        cache = getattr(user, '_compras_grupos_cache', None)
        if cache is None:
            cache = {}
            user._compras_grupos_cache = cache
        if nome not in cache:
            cache[nome] = user.groups.filter(name=nome).exists()
        return cache[nome]

    @classmethod
    def restrito(cls, user):
        return bool(
            cls._autenticado(user)
            and (
                user.get_username().strip().lower() == 'jose.barboza'
                or cls._pertence_ao_grupo(user, GruposCorporativos.COMPRAS_RESTRITO)
            )
        )

    @classmethod
    def _admin_ou_compras(cls, user):
        if not cls._autenticado(user) or cls.restrito(user):
            return False
        perfil = getattr(user, 'perfil', None)
        return bool(
            user.is_superuser
            or (perfil and perfil.is_admin)
            or cls._pertence_ao_grupo(user, GruposInsumos.COMPRAS)
        )

    @classmethod
    def pode_visualizar_valores(cls, user):
        if cls.restrito(user):
            return False
        perfil = getattr(user, 'perfil', None)
        return bool(
            cls._admin_ou_compras(user)
            or user.has_perm('insumos.visualizar_valores_estoque')
            or (
                perfil
                and (perfil.is_financeiro_insumos or perfil.is_executivo_insumos)
            )
        )

    @classmethod
    def pode_editar_precos(cls, user):
        return cls._admin_ou_compras(user) or (
            cls._autenticado(user)
            and not cls.restrito(user)
            and user.has_perm('insumos.gerenciar_precos')
        )

    @classmethod
    def pode_gerenciar_catalogo(cls, user):
        return cls._admin_ou_compras(user)

    @classmethod
    def pode_gerenciar_fornecedores(cls, user):
        return cls._admin_ou_compras(user) or (
            cls._autenticado(user)
            and not cls.restrito(user)
            and user.has_perm('insumos.gerenciar_fornecedores')
        )

    @classmethod
    def pode_criar_remessa(cls, user):
        return cls._admin_ou_compras(user) or (
            cls._autenticado(user)
            and not cls.restrito(user)
            and user.has_perm('insumos.criar_remessa_compra')
        )

    @classmethod
    def empresas(cls, user):
        if not cls._admin_ou_compras(user):
            return Empresa.objects.none()
        perfil = user.perfil
        if user.is_superuser or perfil.is_admin:
            return Empresa.objects.all()
        ids = list(perfil.empresas_escopo_compras.values_list('pk', flat=True))
        if perfil.empresa_id:
            ids.append(perfil.empresa_id)
        return Empresa.objects.filter(pk__in=set(ids))

    @classmethod
    def bases(cls, user):
        if not cls._admin_ou_compras(user):
            return Base.objects.none()
        perfil = user.perfil
        if user.is_superuser or perfil.is_admin:
            return Base.objects.all()
        ids = set(perfil.bases_escopo_compras.values_list('pk', flat=True))
        ids.update(perfil.regionais.values_list('pk', flat=True))
        return Base.objects.filter(
            pk__in=ids,
            empresa__in=cls.empresas(user),
        )
