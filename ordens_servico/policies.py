from django.db.models import Q

from estoque.policies.compras import ComprasAccessPolicy
from ordens_servico.models import OrdemServico


class OrdemServicoAccessPolicy:
    @staticmethod
    def queryset(user):
        if not user or not user.is_authenticated:
            return OrdemServico.objects.none()
        username = user.get_username().strip().lower()
        if username == 'rafael.ribeiro':
            return OrdemServico.objects.filter(tipo=OrdemServico.Tipo.SICK)
        if username == 'jose.barboza':
            return OrdemServico.objects.filter(tipo__in=[
                OrdemServico.Tipo.TRANSFERENCIA,
                OrdemServico.Tipo.EMPRESTIMO,
                OrdemServico.Tipo.SICK,
            ])
        if ComprasAccessPolicy.restrito(user):
            return OrdemServico.objects.none()
        perfil = getattr(user, 'perfil', None)
        if not perfil:
            return OrdemServico.objects.none()
        if user.is_superuser or perfil.is_admin or user.has_perm('ordens_servico.visualizar_todas_ordens_servico'):
            return OrdemServico.objects.all()
        if perfil.is_compras_insumos:
            bases = ComprasAccessPolicy.bases(user)
            return OrdemServico.objects.filter(
                Q(solicitante=user)
                | Q(base_responsavel__in=bases)
                | Q(base_origem__in=bases)
                | Q(base_destino__in=bases)
            ).distinct()
        bases = perfil.regionais.all()
        return OrdemServico.objects.filter(
            Q(solicitante=user)
            | Q(responsavel_operacional=user)
            | Q(recebedor=user)
            | Q(base_responsavel__in=bases)
            | Q(base_origem__in=bases)
            | Q(base_destino__in=bases)
        ).distinct()

    @classmethod
    def pode_visualizar(cls, user, ordem):
        return cls.queryset(user).filter(pk=ordem.pk).exists()

    @staticmethod
    def pode_autorizar(user):
        if not user or not user.is_authenticated or ComprasAccessPolicy.restrito(user):
            return False
        perfil = getattr(user, 'perfil', None)
        return bool(
            user.is_superuser
            or (perfil and (perfil.is_admin or perfil.is_gestor))
            or user.has_perm('ordens_servico.autorizar_ordem_servico')
        )
