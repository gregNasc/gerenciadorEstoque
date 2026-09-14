from django.core.exceptions import PermissionDenied
from django.db.models import F, Q

from estoque.models import (
    Base,
    CapacidadeRelacionamentoEmpresa,
    Emprestimo,
    RelacionamentoEmpresa,
    Sick,
    Transferencia,
)
from estoque.security import secure_base_queryset
from estoque.policies.compras import GruposCorporativos


class TenantOperationPolicy:
    """Escopo tenant para fluxos que movimentam equipamentos entre Bases."""

    VIEW = CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR
    CREATE = CapacidadeRelacionamentoEmpresa.Acao.CRIAR
    MOVE = CapacidadeRelacionamentoEmpresa.Acao.MOVIMENTAR
    APPROVE = CapacidadeRelacionamentoEmpresa.Acao.APROVAR

    @classmethod
    def bases(cls, user, resource, action=VIEW, queryset=None):
        queryset = queryset if queryset is not None else Base.objects.all()
        return secure_base_queryset(
            queryset,
            user,
            resource=resource,
            action=action,
        )

    @classmethod
    def can_access_base(cls, user, base, resource, action=VIEW):
        return cls.bases(user, resource, action).filter(pk=base.pk).exists()

    @classmethod
    def require_base(cls, user, base, resource, action=VIEW):
        if not cls.can_access_base(user, base, resource, action):
            raise PermissionDenied('Usuário sem acesso à base desta operação.')
        return base

    @staticmethod
    def _relationship_exists(origin_company_id, destination_company_id, resource, action):
        if origin_company_id == destination_company_id:
            return True
        return RelacionamentoEmpresa.objects.filter(
            empresa_origem_id=origin_company_id,
            empresa_destino_id=destination_company_id,
            ativo=True,
            capacidades__recurso=resource,
            capacidades__acao=action,
            capacidades__ativo=True,
        ).exists()

    @classmethod
    def flow_allowed(cls, origin, destination, resource, action=MOVE):
        return cls._relationship_exists(
            origin.empresa_id,
            destination.empresa_id,
            resource,
            action,
        )

    @classmethod
    def require_flow(cls, user, origin, destination, resource, action=MOVE):
        cls.require_base(user, origin, resource, action)
        cls.require_base(user, destination, resource, action)
        if not cls.flow_allowed(origin, destination, resource, action):
            raise PermissionDenied(
                'A movimentação entre estas empresas não está autorizada.'
            )

    @classmethod
    def destination_bases(cls, user, origin, resource, action=MOVE):
        candidates = cls.bases(
            user,
            resource,
            action,
            Base.objects.select_related('empresa'),
        )
        allowed_ids = [
            base.pk
            for base in candidates
            if base.pk != origin.pk
            and cls.flow_allowed(origin, base, resource, action)
        ]
        return Base.objects.filter(pk__in=allowed_ids).select_related('empresa')

    @classmethod
    def _valid_flow_filter(cls, resource, action=MOVE):
        condition = Q(
            regional_origem__empresa_id=F('regional_destino__empresa_id')
        )
        relationships = RelacionamentoEmpresa.objects.filter(
            ativo=True,
            capacidades__recurso=resource,
            capacidades__acao=action,
            capacidades__ativo=True,
        ).values_list('empresa_origem_id', 'empresa_destino_id')
        for origin_id, destination_id in relationships:
            condition |= Q(
                regional_origem__empresa_id=origin_id,
                regional_destino__empresa_id=destination_id,
            )
        return condition

    @classmethod
    def _movement_queryset(cls, queryset, user, resource, action=VIEW):
        bases = cls.bases(user, resource, action)
        return queryset.filter(
            Q(regional_origem__in=bases) | Q(regional_destino__in=bases)
        ).filter(cls._valid_flow_filter(resource)).distinct()

    @classmethod
    def emprestimos(cls, user, queryset=None, action=VIEW):
        queryset = queryset if queryset is not None else Emprestimo.objects.all()
        return cls._movement_queryset(
            queryset,
            user,
            CapacidadeRelacionamentoEmpresa.Recurso.EMPRESTIMOS,
            action,
        )

    @classmethod
    def transferencias(cls, user, queryset=None, action=VIEW):
        queryset = queryset if queryset is not None else Transferencia.objects.all()
        return cls._movement_queryset(
            queryset,
            user,
            CapacidadeRelacionamentoEmpresa.Recurso.TRANSFERENCIAS,
            action,
        )

    @classmethod
    def sick(cls, user, queryset=None, action=VIEW):
        queryset = queryset if queryset is not None else Sick.objects.all()
        if getattr(user, 'is_superuser', False):
            return queryset

        perfil = getattr(user, 'perfil', None)
        if perfil is None:
            return queryset.none()

        if user.groups.filter(name=GruposCorporativos.SICK_MANUTENCAO).exists():
            # A equipe de manutenção é funcionalmente multi-base, mas nunca
            # atravessa o tenant principal do próprio perfil.
            bases = Base.objects.filter(empresa_id=perfil.empresa_id)
        else:
            bases = cls.bases(
                user,
                CapacidadeRelacionamentoEmpresa.Recurso.SICK,
                action,
            )
        internal = Q(
            ~Q(tipo_destino=Sick.TipoDestino.TERCEIRIZADA),
            equipamento__regional__in=bases,
        )
        # O fluxo terceirizado permanece estritamente na base de origem e não
        # herda o escopo ampliado de Admin ou de grupos funcionais.
        external = Q(pk__in=[])
        if perfil.is_gestor or perfil.is_operador:
            external = Q(
                tipo_destino=Sick.TipoDestino.TERCEIRIZADA,
                base_origem__in=perfil.regionais.all(),
                equipamento__regional__empresa_id=perfil.empresa_id,
            )
        return queryset.filter(internal | external)
