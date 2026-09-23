from compras.models import CatalogoProdutoEmpresa
from django.db.models import Exists, OuterRef
from estoque.models import CategoriaEquipamentoEmpresa, Empresa, Produto
from estoque.security import secure_tenant_group_company_queryset


class TenantCatalogService:
    """Fonte fail-closed de categorias e produtos visíveis por tenant."""

    @classmethod
    def companies(cls, user, *, company=None):
        companies = secure_tenant_group_company_queryset(
            Empresa.objects.all(),
            user,
        )
        if company is not None:
            companies = companies.filter(pk=getattr(company, 'pk', company))
        return companies

    @classmethod
    def categories(cls, user, *, company=None):
        companies = cls.companies(user, company=company)
        return CategoriaEquipamentoEmpresa.objects.filter(
            empresa__in=companies,
            ativo=True,
        ).order_by('ordem', 'nome', 'pk')

    @classmethod
    def category_names(cls, user, *, company=None):
        names = []
        seen = set()
        for name in cls.categories(user, company=company).values_list(
            'nome', flat=True,
        ):
            normalized = name.strip().casefold()
            if normalized and normalized not in seen:
                seen.add(normalized)
                names.append(name)
        return names

    @classmethod
    def products(cls, user, *, company=None):
        companies = cls.companies(user, company=company)
        active_categories = CategoriaEquipamentoEmpresa.objects.filter(
            empresa_id=OuterRef('empresa_id'),
            nome__iexact=OuterRef('produto__categoria'),
            ativo=True,
        )
        product_ids = CatalogoProdutoEmpresa.objects.filter(
            empresa__in=companies,
            ativo=True,
        ).filter(Exists(active_categories)).values('produto_id')
        return Produto.objects.filter(
            pk__in=product_ids,
            ativo=True,
        ).distinct()

    @classmethod
    def scope_equipment(
        cls, queryset, user, *, company=None, restrict_companies=True,
    ):
        active_categories = CategoriaEquipamentoEmpresa.objects.filter(
            empresa_id=OuterRef('regional__empresa_id'),
            nome__iexact=OuterRef('produto__categoria'),
            ativo=True,
        )
        catalog_entries = CatalogoProdutoEmpresa.objects.filter(
            empresa_id=OuterRef('regional__empresa_id'),
            produto_id=OuterRef('produto_id'),
            ativo=True,
        )
        queryset = queryset.filter(produto__ativo=True)
        if restrict_companies:
            queryset = queryset.filter(
                regional__empresa__in=cls.companies(user, company=company),
            )
        elif company is not None:
            queryset = queryset.filter(
                regional__empresa_id=getattr(company, 'pk', company),
            )
        return queryset.filter(Exists(active_categories), Exists(catalog_entries))
