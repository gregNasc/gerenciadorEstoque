from django.db.models import Q

from chamados.models import Chamado
from estoque.models import Base


class ChamadoAccessPolicy:
    GRUPO_ATENDIMENTO = 'CHAMADOS_ATENDIMENTO'

    @staticmethod
    def perfil(user):
        return getattr(user, 'perfil', None)

    @classmethod
    def pode_atender(cls, user):
        perfil = cls.perfil(user)
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or (perfil and perfil.is_admin)
                or user.has_perm('chamados.atender_chamado')
                or user.groups.filter(name=cls.GRUPO_ATENDIMENTO).exists()
            )
        )

    @classmethod
    def bases(cls, user):
        if not user or not user.is_authenticated:
            return Base.objects.none()
        perfil = cls.perfil(user)
        if user.is_superuser or (perfil and perfil.is_admin):
            return Base.objects.all()
        if not perfil:
            return Base.objects.none()
        filtros = Q(pk__in=perfil.regionais.values('pk')) | Q(pk__in=perfil.bases_escopo_compras.values('pk'))
        if perfil.empresas_escopo_compras.exists():
            filtros |= Q(empresa__in=perfil.empresas_escopo_compras.all())
        return Base.objects.filter(filtros).distinct()

    @classmethod
    def queryset(cls, user):
        if not user or not user.is_authenticated:
            return Chamado.objects.none()
        perfil = cls.perfil(user)
        if user.is_superuser or (perfil and perfil.is_admin):
            return Chamado.objects.all()
        if cls.pode_atender(user) or user.has_perm('chamados.visualizar_todos_chamados'):
            qs = Chamado.objects.all()
            if perfil and perfil.empresa_id:
                qs = qs.filter(empresa_id=perfil.empresa_id)
            return qs
        filtros = Q(aberto_por=user)
        if perfil and perfil.is_gestor:
            filtros |= Q(base__in=cls.bases(user))
        return Chamado.objects.filter(filtros).distinct()

    @classmethod
    def pode_abrir_na_base(cls, user, base):
        return cls.bases(user).filter(pk=base.pk).exists()

    @classmethod
    def pode_ver(cls, user, chamado):
        return cls.queryset(user).filter(pk=chamado.pk).exists()

    @classmethod
    def pode_interagir(cls, user, chamado):
        return cls.pode_atender(user) or chamado.aberto_por_id == user.pk
