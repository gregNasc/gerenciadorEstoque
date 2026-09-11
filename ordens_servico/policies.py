from django.db.models import Q

from estoque.models import Base, CapacidadeRelacionamentoEmpresa, Empresa
from estoque.policies.compras import ComprasAccessPolicy
from estoque.security import secure_base_queryset, secure_company_queryset
from ordens_servico.models import OrdemServico


class OrdemServicoAccessPolicy:
    RESOURCE = CapacidadeRelacionamentoEmpresa.Recurso.ORDENS_SERVICO
    VIEW = CapacidadeRelacionamentoEmpresa.Acao.VISUALIZAR
    CREATE = CapacidadeRelacionamentoEmpresa.Acao.CRIAR
    EDIT = CapacidadeRelacionamentoEmpresa.Acao.EDITAR
    APPROVE = CapacidadeRelacionamentoEmpresa.Acao.APROVAR
    EXPORT = CapacidadeRelacionamentoEmpresa.Acao.EXPORTAR

    @classmethod
    def empresas(cls, user, *, action=VIEW):
        if not user or not user.is_authenticated:
            return Empresa.objects.none()
        if user.is_superuser:
            return Empresa.objects.all()
        perfil = getattr(user, 'perfil', None)
        if not perfil or not perfil.empresa_id:
            return Empresa.objects.none()
        if perfil.is_admin:
            return secure_company_queryset(
                Empresa.objects.all(),
                user,
                resource=cls.RESOURCE,
                action=action,
            )
        ids = {perfil.empresa_id}
        if perfil.is_compras_insumos:
            ids.update(perfil.empresas_escopo_compras.values_list('pk', flat=True))
        return Empresa.objects.filter(pk__in=ids)

    @classmethod
    def bases(cls, user, *, action=VIEW):
        if not user or not user.is_authenticated:
            return Base.objects.none()
        if user.is_superuser:
            return Base.objects.all()
        perfil = getattr(user, 'perfil', None)
        if not perfil:
            return Base.objects.none()
        if perfil.is_admin:
            return secure_base_queryset(
                Base.objects.all(),
                user,
                resource=cls.RESOURCE,
                action=action,
            )
        ids = set(perfil.regionais.values_list('pk', flat=True))
        if perfil.is_compras_insumos:
            ids.update(perfil.bases_escopo_compras.values_list('pk', flat=True))
        return Base.objects.filter(
            pk__in=ids,
            empresa__in=cls.empresas(user, action=action),
        )

    @classmethod
    def queryset(cls, user, *, action=VIEW):
        if not user or not user.is_authenticated:
            return OrdemServico.objects.none()
        if user.is_superuser:
            return OrdemServico.objects.all()
        perfil = getattr(user, 'perfil', None)
        if not perfil:
            return OrdemServico.objects.none()
        empresas = cls.empresas(user, action=action)
        bases = cls.bases(user, action=action)
        escopo_tenant = Q(empresa__in=empresas)
        username = user.get_username().strip().lower()
        if username == 'rafael.ribeiro':
            return OrdemServico.objects.filter(
                escopo_tenant,
                tipo=OrdemServico.Tipo.SICK,
            )
        if username == 'jose.barboza':
            return OrdemServico.objects.filter(escopo_tenant, tipo__in=[
                    OrdemServico.Tipo.TRANSFERENCIA,
                    OrdemServico.Tipo.EMPRESTIMO,
                    OrdemServico.Tipo.SICK,
                ])
        if ComprasAccessPolicy.restrito(user):
            return OrdemServico.objects.none()
        if perfil.is_admin or user.has_perm('ordens_servico.visualizar_todas_ordens_servico'):
            return OrdemServico.objects.filter(escopo_tenant)
        if perfil.is_compras_insumos:
            return OrdemServico.objects.filter(
                escopo_tenant
                & (
                    Q(solicitante=user)
                    | Q(base_responsavel__in=bases)
                    | Q(base_origem__in=bases)
                    | Q(base_destino__in=bases)
                )
            ).distinct()
        return OrdemServico.objects.filter(
            escopo_tenant
            & (
                Q(solicitante=user)
                | Q(responsavel_operacional=user)
                | Q(recebedor=user)
                | Q(base_responsavel__in=bases)
                | Q(base_origem__in=bases)
                | Q(base_destino__in=bases)
            )
        ).distinct()

    @classmethod
    def pode_visualizar(cls, user, ordem):
        return cls.queryset(user).filter(pk=ordem.pk).exists()

    @classmethod
    def pode_autorizar(cls, user, ordem=None):
        if not user or not user.is_authenticated or ComprasAccessPolicy.restrito(user):
            return False
        perfil = getattr(user, 'perfil', None)
        permitido = bool(
            user.is_superuser
            or (perfil and (perfil.is_admin or perfil.is_gestor))
            or user.has_perm('ordens_servico.autorizar_ordem_servico')
        )
        if not permitido:
            return False
        if ordem is None:
            return cls.queryset(user, action=cls.APPROVE).exists()
        return cls.queryset(user, action=cls.APPROVE).filter(pk=ordem.pk).exists()
