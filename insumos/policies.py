from django.core.exceptions import PermissionDenied
from django.db.models import Q

from estoque.models import Base, CapacidadeRelacionamentoEmpresa, Empresa
from estoque.security import secure_base_queryset, secure_company_queryset


class InsumosTenantPolicy:
    """Escopo de dados da Etapa 15, separado da permissão funcional."""

    VIEW = CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR
    CREATE = CapacidadeRelacionamentoEmpresa.Acao.CRIAR
    EDIT = CapacidadeRelacionamentoEmpresa.Acao.EDITAR
    MOVE = CapacidadeRelacionamentoEmpresa.Acao.MOVIMENTAR
    APPROVE = CapacidadeRelacionamentoEmpresa.Acao.APROVAR
    EXPORT = CapacidadeRelacionamentoEmpresa.Acao.EXPORTAR

    SUPPLIES = CapacidadeRelacionamentoEmpresa.Recurso.INSUMOS
    CHECKLISTS = CapacidadeRelacionamentoEmpresa.Recurso.CHECKLISTS
    INVENTORIES = CapacidadeRelacionamentoEmpresa.Recurso.INVENTARIOS

    @classmethod
    def empresas(cls, user, *, action=VIEW, queryset=None):
        queryset = queryset if queryset is not None else Empresa.objects.all()
        return secure_company_queryset(
            queryset,
            user,
            resource=cls.SUPPLIES,
            action=action,
        )

    @classmethod
    def prices(cls, user, queryset, *, action=VIEW):
        if getattr(user, 'is_superuser', False):
            return queryset
        empresas = cls.empresas(user, action=action)
        return queryset.filter(
            Q(empresa__in=empresas)
            | Q(
                empresa=None,
                cadastrado_por__perfil__empresa__in=empresas,
            )
        ).distinct()

    @classmethod
    def price_searches(cls, user, queryset, *, action=VIEW):
        if getattr(user, 'is_superuser', False):
            return queryset
        empresas = cls.empresas(user, action=action)
        return queryset.filter(
            Q(empresa__in=empresas)
            | Q(
                empresa=None,
                pesquisado_por__perfil__empresa__in=empresas,
            )
        ).distinct()

    @classmethod
    def price_offers(cls, user, queryset, *, action=VIEW):
        pesquisas = cls.price_searches(
            user,
            queryset.model._meta.get_field('pesquisa').related_model.objects.all(),
            action=action,
        )
        return queryset.filter(pesquisa__in=pesquisas)

    @classmethod
    def bases(cls, user, *, resource=SUPPLIES, action=VIEW, queryset=None):
        queryset = queryset if queryset is not None else Base.objects.all()
        profile = getattr(user, 'perfil', None)
        if (
            resource == cls.CHECKLISTS
            and profile is not None
            and not getattr(user, 'is_superuser', False)
            and not profile.is_admin
        ):
            if not profile.empresa_id:
                return queryset.none()
            return queryset.filter(
                pk__in=profile.bases_checklist_ativas.values_list('pk', flat=True),
                empresa_id=profile.empresa_id,
            )
        return secure_base_queryset(
            queryset,
            user,
            resource=resource,
            action=action,
        )

    @classmethod
    def queryset(
        cls,
        queryset,
        user,
        *,
        base_field='base',
        resource=SUPPLIES,
        action=VIEW,
    ):
        bases = cls.bases(user, resource=resource, action=action)
        return queryset.filter(**{f'{base_field}__in': bases}).distinct()

    @classmethod
    def inventories(cls, user, queryset, *, action=VIEW):
        return cls.queryset(
            queryset,
            user,
            base_field='base',
            resource=cls.INVENTORIES,
            action=action,
        )

    @classmethod
    def checklists(cls, user, queryset, *, action=VIEW):
        return cls.queryset(
            queryset,
            user,
            base_field='inventario__base',
            resource=cls.CHECKLISTS,
            action=action,
        )

    @classmethod
    def requests(cls, user, queryset, *, action=VIEW):
        return cls.queryset(
            queryset,
            user,
            base_field='base',
            resource=cls.SUPPLIES,
            action=action,
        )

    @classmethod
    def movements(cls, user, queryset, *, action=VIEW):
        return cls.queryset(
            queryset,
            user,
            base_field='base',
            resource=cls.SUPPLIES,
            action=action,
        )

    @classmethod
    def balances(cls, user, queryset, *, action=VIEW):
        return cls.queryset(
            queryset,
            user,
            base_field='base',
            resource=cls.SUPPLIES,
            action=action,
        )

    @classmethod
    def lots(cls, user, queryset, *, action=VIEW):
        return cls.queryset(
            queryset,
            user,
            base_field='base',
            resource=cls.CHECKLISTS,
            action=action,
        )

    @classmethod
    def consumptions(cls, user, queryset, *, action=VIEW):
        return cls.queryset(
            queryset,
            user,
            base_field='inventario__base',
            resource=cls.SUPPLIES,
            action=action,
        )

    @classmethod
    def histories(cls, user, queryset, *, action=VIEW):
        """Históricos sem base são globais e ficam exclusivos ao superuser."""
        if getattr(user, 'is_superuser', False):
            return queryset
        return cls.queryset(
            queryset,
            user,
            base_field='base',
            resource=cls.SUPPLIES,
            action=action,
        )

    @classmethod
    def can_access_base(cls, user, base, *, resource=SUPPLIES, action=VIEW):
        return cls.bases(
            user,
            resource=resource,
            action=action,
        ).filter(pk=base.pk).exists()

    @classmethod
    def require_base(cls, user, base, *, resource=SUPPLIES, action=VIEW):
        if not cls.can_access_base(
            user,
            base,
            resource=resource,
            action=action,
        ):
            raise PermissionDenied('Usuário sem acesso à base desta operação.')
        return base
