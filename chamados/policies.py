from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from chamados.models import Chamado
from estoque.models import Base


class GruposChamados:
    SUPORTE = 'CHAMADOS_SUPORTE'
    SUPERVISOR = 'CHAMADOS_SUPERVISOR'
    DASHBOARD = 'CHAMADOS_DASHBOARD'
    CONFIGURACAO = 'CHAMADOS_CONFIGURACAO'
    LEGADO_ATENDIMENTO = 'CHAMADOS_ATENDIMENTO'
    TODOS = (SUPORTE, SUPERVISOR, DASHBOARD, CONFIGURACAO)


class ChamadoAccessPolicy:
    GRUPO_ATENDIMENTO = GruposChamados.LEGADO_ATENDIMENTO

    @staticmethod
    def perfil(user):
        return getattr(user, 'perfil', None)

    @staticmethod
    def _grupo(user, *nomes):
        return bool(
            user and user.is_authenticated
            and user.groups.filter(name__in=nomes).exists()
        )

    @classmethod
    def e_admin(cls, user):
        perfil = cls.perfil(user)
        return bool(user and user.is_authenticated and (user.is_superuser or (perfil and perfil.is_admin)))

    @classmethod
    def pode_atender(cls, user):
        return bool(
            cls.e_admin(user)
            or user.has_perm('chamados.atender_chamado')
            or cls._grupo(
                user, GruposChamados.SUPORTE, GruposChamados.SUPERVISOR,
                GruposChamados.LEGADO_ATENDIMENTO,
            )
        )

    @classmethod
    def pode_supervisionar(cls, user):
        return bool(
            cls.e_admin(user)
            or user.has_perm('chamados.supervisionar_chamado')
            or cls._grupo(user, GruposChamados.SUPERVISOR)
        )

    @classmethod
    def pode_dashboard(cls, user):
        return bool(
            cls.e_admin(user)
            or user.has_perm('chamados.visualizar_dashboard_chamado')
            or user.has_perm('chamados.exportar_chamados')
            or cls._grupo(user, GruposChamados.DASHBOARD, GruposChamados.SUPERVISOR)
        )

    @classmethod
    def pode_configurar(cls, user):
        return bool(
            cls.e_admin(user)
            or user.has_perm('chamados.configurar_chamado')
            or cls._grupo(user, GruposChamados.CONFIGURACAO)
        )

    @classmethod
    def bases(cls, user):
        if not user or not user.is_authenticated:
            return Base.objects.none()
        perfil = cls.perfil(user)
        if cls.e_admin(user):
            return Base.objects.all()
        if not perfil:
            return Base.objects.none()
        return perfil.regionais.all()

    @classmethod
    def queryset(cls, user):
        if not user or not user.is_authenticated:
            return Chamado.objects.none()
        if cls.e_admin(user):
            return Chamado.objects.all()
        perfil = cls.perfil(user)
        if (
            cls.pode_atender(user)
            or user.has_perm('chamados.visualizar_todos_chamados')
            or (perfil and perfil.is_gestor)
        ):
            return Chamado.objects.filter(base__in=cls.bases(user)).distinct()
        return Chamado.objects.filter(aberto_por=user)

    @classmethod
    def pode_abrir_na_base(cls, user, base):
        perfil = cls.perfil(user)
        return bool(
            perfil
            and not cls.e_admin(user)
            and (
                perfil.is_gestor
                or perfil.is_operador
                or user.has_perm('chamados.abrir_chamado')
            )
            and cls.bases(user).filter(pk=base.pk).exists()
        )

    @classmethod
    def pode_ver(cls, user, chamado):
        return cls.queryset(user).filter(pk=chamado.pk).exists()

    @classmethod
    def pode_interagir(cls, user, chamado):
        return bool(
            chamado.atendente_id
            and (
                chamado.aberto_por_id == getattr(user, 'pk', None)
                or chamado.atendente_id == getattr(user, 'pk', None)
                or cls.pode_supervisionar(user)
            )
        )

    @classmethod
    def pode_transferir(cls, user, chamado):
        return bool(
            cls.pode_supervisionar(user)
            or chamado.atendente_id == getattr(user, 'pk', None)
        )

    @classmethod
    def atendentes_para(cls, chamado):
        from django.contrib.auth.models import User

        return User.objects.filter(is_active=True).filter(
            Q(perfil__role='admin')
            | Q(groups__name__in=[GruposChamados.SUPORTE, GruposChamados.SUPERVISOR])
            | Q(user_permissions__codename='atender_chamado')
        ).filter(
            Q(perfil__role='admin') | Q(perfil__regionais=chamado.base)
        ).distinct()

    @classmethod
    def atendentes_online_para(cls, chamado=None):
        from django.contrib.auth.models import User

        limite = timezone.now() - timedelta(seconds=90)
        ids = User.objects.filter(
            conexoes_presenca_chamados__visto_em__gte=limite,
        ).values_list('pk', flat=True)
        if chamado is None:
            return User.objects.filter(pk__in=ids, is_active=True).filter(
                Q(perfil__role='admin')
                | Q(groups__name__in=[GruposChamados.SUPORTE, GruposChamados.SUPERVISOR])
                | Q(user_permissions__codename='atender_chamado')
            ).distinct()
        return cls.atendentes_para(chamado).filter(pk__in=ids)

    @classmethod
    def pode_converter_sick(cls, user, chamado):
        return bool(
            chamado.equipamento_id
            and cls.pode_ver(user, chamado)
            and (
                cls.e_admin(user)
                or cls.pode_supervisionar(user)
                or (
                    chamado.atendente_id == getattr(user, 'pk', None)
                    and (
                        cls.pode_atender(user)
                        or user.has_perm('chamados.converter_chamado_sick')
                    )
                )
            )
        )
