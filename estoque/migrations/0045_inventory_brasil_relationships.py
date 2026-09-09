from django.db import migrations
from django.db.models import Q


COMPANY_SPECS = {
    'brasil': ('inventory-brasil', 'Inventory Brasil'),
    'latam': ('inventory-latam', 'Inventory Latam'),
    'oxxo': ('oxxo', 'OXXO'),
}

DOMAIN_RESOURCES = (
    'EQUIPAMENTOS',
    'ESTOQUE',
    'SICK',
    'TRANSFERENCIAS',
    'EMPRESTIMOS',
    'INSUMOS',
    'CHECKLISTS',
    'INVENTARIOS',
    'CHAMADOS',
    'COMPRAS',
    'CATALOGO',
    'ORDENS_SERVICO',
    'AUDITORIAS',
    'DOCUMENTACAO',
    'INTEGRACOES',
    'TORY',
    'USUARIOS',
)

DOMAIN_ACTIONS = (
    'VISUALIZAR',
    'CRIAR',
    'EDITAR',
    'MOVIMENTAR',
    'ATENDER',
    'APROVAR',
    'EXPORTAR',
    'ADMINISTRAR',
)

FULL_OPERATIONAL_CAPABILITIES = frozenset(
    [('OPERACAO', 'ADMINISTRAR')]
    + [
        (resource, action)
        for resource in DOMAIN_RESOURCES
        for action in DOMAIN_ACTIONS
    ]
)


def _resolve_companies(Empresa):
    matches = {}
    for key, (slug, name) in COMPANY_SPECS.items():
        matches[key] = list(
            Empresa.objects.filter(
                Q(slug__iexact=slug) | Q(nome__iexact=name)
            ).order_by('pk')
        )

    counts = {key: len(items) for key, items in matches.items()}
    if all(count == 0 for count in counts.values()):
        # Uma instalacao nova ainda nao possui dados organizacionais para migrar.
        return None
    if any(count != 1 for count in counts.values()):
        raise RuntimeError(
            'Não foi possível identificar de forma inequívoca Inventory Brasil, '
            f'Inventory Latam e OXXO. Correspondências: {counts}.'
        )

    companies = {key: items[0] for key, items in matches.items()}
    if len({company.pk for company in companies.values()}) != len(companies):
        raise RuntimeError(
            'Os tenants Inventory Brasil, Inventory Latam e OXXO devem ser distintos.'
        )
    return companies


def _ensure_full_capabilities(Capability, relationship):
    existing = set(
        Capability.objects.filter(relacionamento=relationship).values_list(
            'recurso', 'acao'
        )
    )
    Capability.objects.bulk_create([
        Capability(
            relacionamento=relationship,
            recurso=resource,
            acao=action,
            ativo=True,
        )
        for resource, action in FULL_OPERATIONAL_CAPABILITIES - existing
    ])

    Capability.objects.filter(
        relacionamento=relationship,
    ).filter(
        Q(recurso='OPERACAO', acao='ADMINISTRAR')
        | Q(recurso__in=DOMAIN_RESOURCES, acao__in=DOMAIN_ACTIONS)
    ).update(ativo=True)

    active_count = Capability.objects.filter(
        relacionamento=relationship,
        ativo=True,
    ).filter(
        Q(recurso='OPERACAO', acao='ADMINISTRAR')
        | Q(recurso__in=DOMAIN_RESOURCES, acao__in=DOMAIN_ACTIONS)
    ).count()
    if active_count != len(FULL_OPERATIONAL_CAPABILITIES):
        raise RuntimeError(
            f'Capabilities incompletas no relacionamento {relationship.pk}.'
        )


def create_inventory_brasil_relationships(apps, schema_editor):
    Empresa = apps.get_model('estoque', 'Empresa')
    Relationship = apps.get_model('estoque', 'RelacionamentoEmpresa')
    Capability = apps.get_model('estoque', 'CapacidadeRelacionamentoEmpresa')

    companies = _resolve_companies(Empresa)
    if companies is None:
        return

    for destination_key in ('latam', 'oxxo'):
        relationship, _created = Relationship.objects.get_or_create(
            empresa_origem=companies['brasil'],
            empresa_destino=companies[destination_key],
            defaults={'ativo': True},
        )
        if not relationship.ativo:
            Relationship.objects.filter(pk=relationship.pk).update(ativo=True)
            relationship.ativo = True
        _ensure_full_capabilities(Capability, relationship)


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0044_relacionamentoempresa_and_more'),
    ]

    operations = [
        migrations.RunPython(
            create_inventory_brasil_relationships,
            migrations.RunPython.noop,
        ),
    ]
