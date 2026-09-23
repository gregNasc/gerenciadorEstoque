from django.db.models import Exists, OuterRef

from compras.models import CatalogoProdutoEmpresa
from estoque.models import CategoriaEquipamentoEmpresa


class ChecklistCatalogService:
    @staticmethod
    def categories(base):
        return CategoriaEquipamentoEmpresa.objects.filter(
            empresa_id=base.empresa_id, ativo=True,
        ).order_by('ordem', 'nome', 'pk')

    @staticmethod
    def equipment(queryset):
        categories = CategoriaEquipamentoEmpresa.objects.filter(
            empresa_id=OuterRef('regional__empresa_id'),
            nome__iexact=OuterRef('produto__categoria'), ativo=True,
        )
        catalog = CatalogoProdutoEmpresa.objects.filter(
            empresa_id=OuterRef('regional__empresa_id'),
            produto_id=OuterRef('produto_id'), ativo=True,
        )
        return queryset.filter(produto__ativo=True).filter(Exists(categories), Exists(catalog))

    @classmethod
    def context(cls, bases, equipment):
        rows = []
        equipment = list(cls.equipment(equipment).select_related('produto', 'regional'))
        for category in CategoriaEquipamentoEmpresa.objects.filter(
            empresa_id__in=bases.values('empresa_id'), ativo=True,
        ).order_by('ordem', 'nome', 'pk'):
            rows.append({
                'key': f'categoria_{category.pk}',
                'nome': category.nome,
                'empresa_id': category.empresa_id,
                'equipamentos': [
                    eq for eq in equipment
                    if eq.regional.empresa_id == category.empresa_id
                    and eq.produto.categoria.casefold() == category.nome.casefold()
                ],
            })
        return rows

    @staticmethod
    def limit(category, people):
        margin = category.limite_checklist_por_pessoas
        return people + margin if margin is not None and people is not None else None
