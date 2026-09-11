from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from chamados.models import Chamado
from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Empresa,
    RelacionamentoEmpresa,
)
from estoque.security import secure_base_queryset, secure_company_queryset


class GruposChamados:
    SUPORTE = 'CHAMADOS_SUPORTE'
    SUPERVISOR = 'CHAMADOS_SUPERVISOR'
    DASHBOARD = 'CHAMADOS_DASHBOARD'
    CONFIGURACAO = 'CHAMADOS_CONFIGURACAO'
    LEGADO_ATENDIMENTO = 'CHAMADOS_ATENDIMENTO'
    TODOS = (SUPORTE, SUPERVISOR, DASHBOARD, CONFIGURACAO)


class ChamadoAccessPolicy:
    GRUPO_ATENDIMENTO = GruposChamados.LEGADO_ATENDIMENTO
    RESOURCE = CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS
    VIEW = CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR
    CREATE = CapacidadeRelacionamentoEmpresa.Acao.CRIAR
    ATTEND = CapacidadeRelacionamentoEmpresa.Acao.ATENDER
    EXPORT = CapacidadeRelacionamentoEmpresa.Acao.EXPORTAR
    ADMIN = CapacidadeRelacionamentoEmpresa.Acao.ADMINISTRAR

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
    def bases(cls, user, *, action=VIEW):
        if not user or not user.is_authenticated:
            return Base.objects.none()
        return secure_base_queryset(
            Base.objects.all(),
            user,
            resource=cls.RESOURCE,
            action=action,
        )

    @classmethod
    def empresas(cls, user, *, action=VIEW):
        if not user or not user.is_authenticated:
            return Empresa.objects.none()
        return secure_company_queryset(
            Empresa.objects.all(),
            user,
            resource=cls.RESOURCE,
            action=action,
        )

    @classmethod
    def empresas_suporte_compartilhado(cls, user):
        """Empresas do grupo configurado para o checkbox Suporte."""
        if not cls._grupo(user, GruposChamados.SUPORTE):
            return Empresa.objects.none()

        relacionamentos = RelacionamentoEmpresa.objects.filter(
            ativo=True,
            compartilha_suporte_chamados=True,
            capacidades__ativo=True,
            capacidades__recurso=CapacidadeRelacionamentoEmpresa.Recurso.CHAMADOS,
            capacidades__acao=CapacidadeRelacionamentoEmpresa.Acao.ATENDER,
        )
        ids_origem = relacionamentos.values('empresa_origem_id')
        ids_destino = relacionamentos.values('empresa_destino_id')
        return Empresa.objects.filter(
            Q(pk__in=ids_origem) | Q(pk__in=ids_destino)
        ).distinct()

    @classmethod
    def bases_atendimento(cls, user):
        bases = cls.bases(user, action=cls.ATTEND)
        empresas = cls.empresas_suporte_compartilhado(user)
        if not empresas.exists():
            return bases
        return Base.objects.filter(
            Q(pk__in=bases.values('pk')) | Q(empresa__in=empresas)
        ).distinct()

    @classmethod
    def empresas_atendimento(cls, user):
        ids = set(
            cls.empresas(user, action=cls.ATTEND).values_list('pk', flat=True)
        )
        ids.update(
            cls.empresas_suporte_compartilhado(user).values_list('pk', flat=True)
        )
        return Empresa.objects.filter(pk__in=ids)

    @classmethod
    def bases_visiveis(cls, user):
        ids = set(cls.bases(user, action=cls.VIEW).values_list('pk', flat=True))
        if cls.pode_atender(user):
            ids.update(cls.bases_atendimento(user).values_list('pk', flat=True))
        return Base.objects.filter(pk__in=ids)

    @classmethod
    def empresas_visiveis(cls, user):
        ids = set(
            cls.empresas(user, action=cls.VIEW).values_list('pk', flat=True)
        )
        if cls.pode_atender(user):
            ids.update(
                cls.empresas_atendimento(user).values_list('pk', flat=True)
            )
        return Empresa.objects.filter(pk__in=ids)

    @classmethod
    def queryset(cls, user, *, action=VIEW):
        if not user or not user.is_authenticated:
            return Chamado.objects.none()
        if user.is_superuser:
            return Chamado.objects.all()
        perfil = cls.perfil(user)
        if action == cls.ATTEND:
            if not cls.pode_atender(user):
                return Chamado.objects.none()
            bases = cls.bases_atendimento(user)
            empresas = cls.empresas_atendimento(user)
            escopo = Q(base__in=bases)
            if empresas.exists():
                escopo |= Q(
                    tipo_chamado=Chamado.Tipo.REPARACAO,
                    empresa__in=empresas,
                )
            return Chamado.objects.filter(escopo).distinct()

        bases = (
            cls.bases_visiveis(user)
            if action == cls.VIEW
            else cls.bases(user, action=action)
        )
        empresas = (
            cls.empresas_visiveis(user)
            if action == cls.VIEW
            else cls.empresas(user, action=action)
        )
        escopo = Q(base__in=bases)
        if empresas.exists():
            escopo |= Q(
                tipo_chamado=Chamado.Tipo.REPARACAO,
                empresa__in=empresas,
            )

        if action == cls.EXPORT or user.has_perm(
            'chamados.visualizar_todos_chamados'
        ) or (
            perfil and perfil.is_gestor
        ) or cls.pode_atender(user):
            return Chamado.objects.filter(escopo).distinct()

        return Chamado.objects.filter(aberto_por=user).filter(
            escopo
        ).distinct()

    @classmethod
    def pode_abrir(cls, user):
        perfil = cls.perfil(user)
        return bool(
            user and user.is_authenticated and perfil
            and (
                cls.e_admin(user)
                or perfil.is_gestor
                or perfil.is_operador
                or user.has_perm('chamados.abrir_chamado')
            )
        )

    @classmethod
    def pode_abrir_reparacao(cls, user):
        perfil = cls.perfil(user)
        return bool(cls.pode_abrir(user) and perfil and not perfil.is_operador)

    @classmethod
    def pode_abrir_na_base(cls, user, base):
        perfil = cls.perfil(user)
        return bool(
            perfil
            and (
                cls.e_admin(user)
                or perfil.is_gestor
                or perfil.is_operador
                or user.has_perm('chamados.abrir_chamado')
            )
            and base
            and cls.bases(user, action=cls.CREATE).filter(pk=base.pk).exists()
        )

    @classmethod
    def pode_ver(cls, user, chamado):
        return cls.queryset(user).filter(pk=chamado.pk).exists()

    @classmethod
    def pode_atender_chamado(cls, user, chamado):
        return bool(
            cls.pode_atender(user)
            and cls.queryset(user, action=cls.ATTEND).filter(pk=chamado.pk).exists()
        )

    @classmethod
    def pode_supervisionar_chamado(cls, user, chamado):
        return bool(
            cls.pode_supervisionar(user)
            and cls.pode_atender_chamado(user, chamado)
        )

    @classmethod
    def pode_interagir(cls, user, chamado):
        return bool(
            cls.pode_ver(user, chamado)
            and
            chamado.tipo_chamado == Chamado.Tipo.OPERACIONAL
            and
            chamado.atendente_id
            and (
                chamado.aberto_por_id == getattr(user, 'pk', None)
                or chamado.atendente_id == getattr(user, 'pk', None)
                or cls.pode_supervisionar_chamado(user, chamado)
            )
        )

    @classmethod
    def pode_transferir(cls, user, chamado):
        return bool(
            cls.pode_ver(user, chamado)
            and (
                cls.pode_supervisionar_chamado(user, chamado)
                or chamado.atendente_id == getattr(user, 'pk', None)
            )
        )

    @classmethod
    def atendentes_para(cls, chamado):
        from django.contrib.auth.models import User

        candidatos = User.objects.filter(is_active=True).filter(
            Q(is_superuser=True)
            |
            Q(perfil__role='admin')
            | Q(groups__name__in=[GruposChamados.SUPORTE, GruposChamados.SUPERVISOR])
            | Q(user_permissions__codename='atender_chamado')
        ).distinct()
        ids = [
            candidato.pk
            for candidato in candidatos
            if cls.pode_atender(candidato)
            and cls.queryset(candidato, action=cls.ATTEND).filter(
                pk=chamado.pk
            ).exists()
        ]
        return User.objects.filter(pk__in=ids, is_active=True)

    @classmethod
    def admins_para(cls, chamado):
        from django.contrib.auth.models import User

        candidatos = User.objects.filter(is_active=True).filter(
            Q(is_superuser=True) | Q(perfil__role='admin')
        ).distinct()
        ids = [
            candidato.pk
            for candidato in candidatos
            if cls.queryset(candidato).filter(pk=chamado.pk).exists()
        ]
        return User.objects.filter(pk__in=ids, is_active=True)

    @classmethod
    def atendentes_online_para(cls, chamado=None, *, user=None):
        from django.contrib.auth.models import User

        limite = timezone.now() - timedelta(seconds=90)
        ids = User.objects.filter(
            conexoes_presenca_chamados__visto_em__gte=limite,
        ).values_list('pk', flat=True)
        if chamado is None:
            candidatos = User.objects.filter(pk__in=ids, is_active=True).filter(
                Q(is_superuser=True)
                |
                Q(perfil__role='admin')
                | Q(groups__name__in=[GruposChamados.SUPORTE, GruposChamados.SUPERVISOR])
                | Q(user_permissions__codename='atender_chamado')
            ).distinct()
            if user is None:
                return candidatos.none()
            bases_usuario = set(
                cls.bases(user, action=cls.CREATE).values_list('pk', flat=True)
            )
            empresas_usuario = set(
                cls.empresas(user, action=cls.CREATE).values_list('pk', flat=True)
            )
            candidatos_ids = []
            for candidato in candidatos:
                if not cls.pode_atender(candidato):
                    continue
                bases_candidato = set(
                    cls.bases_atendimento(candidato).values_list('pk', flat=True)
                )
                empresas_candidato = set(
                    cls.empresas_atendimento(candidato).values_list('pk', flat=True)
                )
                if (
                    bases_usuario & bases_candidato
                    or empresas_usuario & empresas_candidato
                ):
                    candidatos_ids.append(candidato.pk)
            return User.objects.filter(pk__in=candidatos_ids, is_active=True)
        return cls.atendentes_para(chamado).filter(pk__in=ids)

    @classmethod
    def pode_converter_sick(cls, user, chamado):
        return bool(
            chamado.equipamento_id
            and cls.pode_atender_chamado(user, chamado)
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
