from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.db import models

from estoque.models import (
    Base,
    CredencialLinhaMovel,
    Empresa,
    LinhaMovel,
    OperadoraMovel,
    Perfil,
)
from estoque.tenant_scope import TenantScope


class LinhasMoveisAccessPolicy:
    VIEW = 'visualizar'
    MANAGE = 'gerenciar'
    LINK = 'vincular'
    VIEW_SECRETS = 'visualizar_credenciais'

    PERMISSOES = {
        VIEW: 'estoque.visualizar_linhas_moveis',
        MANAGE: 'estoque.gerenciar_linhas_moveis',
        LINK: 'estoque.vincular_linhas_moveis',
        VIEW_SECRETS: 'estoque.visualizar_credenciais_linhas_moveis',
    }

    @staticmethod
    def _perfil(user):
        if not user or not user.is_authenticated:
            return None
        return getattr(user, 'perfil', None)

    @classmethod
    def permite(cls, user, action):
        permissao = cls.PERMISSOES.get(action)

        if permissao is None or not user or not user.is_authenticated:
            return False

        perfil = cls._perfil(user)

        # Credenciais sensíveis:
        # somente Admin/Superuser com permissão dedicada.
        if action == cls.VIEW_SECRETS:
            return bool(
                (
                        user.is_superuser
                        or (
                                perfil
                                and perfil.role == Perfil.Role.ADMIN
                        )
                )
                and user.has_perm(permissao)
            )

        # Admin/Superuser administra completamente linhas móveis.
        if user.is_superuser or (
                perfil
                and perfil.role == Perfil.Role.ADMIN
        ):
            return True

        # Gestor pode apenas visualizar o necessário
        # e administrar o vínculo linha <-> equipamento.
        if perfil and perfil.role == Perfil.Role.GESTOR:
            return action in {
                cls.VIEW,
                cls.LINK,
            }

        # Operador permanece sem acesso.
        return False

    @classmethod
    def exigir(cls, user, action):
        if not cls.permite(user, action):
            raise PermissionDenied('Usuário sem permissão para esta operação de linha móvel.')

    @classmethod
    def _company_ids(cls, user, action, *, scope=None):
        if not isinstance(scope, TenantScope) or scope.user_id != user.pk:
            scope = TenantScope.fresh_for_user(user)
        if scope.is_platform_scope:
            return None
        perfil = cls._perfil(user)
        if perfil and perfil.role in {Perfil.Role.GESTOR, Perfil.Role.OPERADOR}:
            return frozenset((perfil.empresa_id,)) if perfil.empresa_id else frozenset()
        if action == cls.VIEW:
            return scope.visible_company_ids
        return scope.manageable_company_ids

    @classmethod
    def empresas(cls, user, *, action=VIEW, queryset=None, scope=None):
        from compras.models import CapacidadeCatalogoProdutoEmpresa

        queryset = queryset if queryset is not None else Empresa.objects.all()
        if not cls.permite(user, action):
            return queryset.none()
        company_ids = cls._company_ids(user, action, scope=scope)
        if company_ids is not None:
            if not company_ids:
                return queryset.none()
            queryset = queryset.filter(pk__in=company_ids)
        empresas_habilitadas = CapacidadeCatalogoProdutoEmpresa.objects.filter(
            catalogo__empresa_id=models.OuterRef('pk'),
            catalogo__ativo=True,
            catalogo__produto__ativo=True,
            codigo__in=(
                CapacidadeCatalogoProdutoEmpresa.CONECTIVIDADE_MOVEL,
                CapacidadeCatalogoProdutoEmpresa.ATIVO_LINHA_MOVEL,
            ),
            ativa=True,
        )
        return queryset.filter(ativa=True).annotate(
            possui_conectividade_movel=models.Exists(empresas_habilitadas),
        ).filter(possui_conectividade_movel=True)

    @classmethod
    def bases(cls, user, *, action=VIEW, empresa=None, queryset=None):
        queryset = queryset if queryset is not None else Base.objects.all()
        empresas = cls.empresas(user, action=action)
        queryset = queryset.filter(empresa__in=empresas)
        if empresa is not None:
            queryset = queryset.filter(empresa=empresa)
        perfil = cls._perfil(user)
        if user.is_superuser or (perfil and perfil.role == Perfil.Role.ADMIN):
            return queryset.order_by('empresa__nome', 'nome')
        if perfil is None:
            return queryset.none()
        return queryset.filter(
            pk__in=perfil.regionais.values_list('pk', flat=True),
        ).order_by('empresa__nome', 'nome')

    @classmethod
    def linhas(cls, user, *, action=VIEW, queryset=None):
        queryset = queryset if queryset is not None else LinhaMovel.objects.all()
        if not cls.permite(user, action):
            return queryset.none()

        queryset = queryset.filter(empresa__in=cls.empresas(user, action=action))

        perfil = cls._perfil(user)
        if user.is_superuser or (perfil and perfil.role == Perfil.Role.ADMIN):
            return queryset
        if perfil is None:
            return queryset.none()

        base_ids = perfil.regionais.values_list('pk', flat=True)
        queryset = queryset.filter(base_id__in=base_ids)
        if perfil.role == Perfil.Role.OPERADOR:
            if action != cls.VIEW:
                return queryset.none()
            queryset = queryset.filter(
                vinculos_equipamento__fim_em__isnull=True,
                vinculos_equipamento__equipamento__regional_id__in=base_ids,
            )
            return queryset.distinct()
        return queryset

    @classmethod
    def operadoras(cls, user, *, action=MANAGE, queryset=None):
        queryset = queryset if queryset is not None else OperadoraMovel.objects.all()
        if not cls.permite(user, action):
            return queryset.none()
        return queryset.filter(empresa__in=cls.empresas(user, action=action))

    @classmethod
    def usuarios_responsaveis(cls, user, *, empresa, base=None, queryset=None):
        queryset = queryset if queryset is not None else User.objects.all()
        if not cls.empresas(user, action=cls.MANAGE).filter(pk=empresa.pk).exists():
            return queryset.none()
        return queryset.filter(
            is_active=True,
            is_superuser=False,
        ).distinct().order_by('first_name', 'last_name', 'username')

    @classmethod
    def credenciais(cls, user, queryset=None):
        queryset = queryset if queryset is not None else CredencialLinhaMovel.objects.all()
        if not cls.permite(user, cls.VIEW_SECRETS):
            return queryset.none()
        linhas = cls.linhas(user, action=cls.VIEW)
        return queryset.filter(linha__in=linhas)

    @classmethod
    def obter_linha(cls, user, linha_id, *, action=VIEW, for_update=False):
        queryset = LinhaMovel.objects.select_related('empresa', 'base', 'operadora')
        if for_update:
            queryset = queryset.select_for_update()
        try:
            return cls.linhas(user, action=action, queryset=queryset).get(pk=linha_id)
        except LinhaMovel.DoesNotExist as exc:
            raise PermissionDenied('Linha móvel inexistente ou fora do escopo.') from exc

