from django.db import migrations, models


COMPANY_SPECS = (
    ('inventory-brasil', 'Inventory Brasil'),
    ('inventory-latam', 'Inventory Latam'),
    ('oxxo', 'OXXO'),
)


def preserve_inventory_legacy_library(apps, schema_editor):
    """Converte a compatibilidade histórica em configuração persistida."""
    Empresa = apps.get_model('estoque', 'Empresa')
    Secao = apps.get_model('estoque', 'SecaoDocumentacaoEmpresa')
    using = schema_editor.connection.alias
    companies = []
    for slug, name in COMPANY_SPECS:
        matches = list(
            Empresa.objects.using(using).filter(
                models.Q(slug__iexact=slug) | models.Q(nome__iexact=name)
            ).order_by('pk')
        )
        if not matches:
            continue
        if len(matches) != 1:
            raise RuntimeError(
                f'Empresa histórica ambígua para {name}: {len(matches)} registros.'
            )
        companies.append(matches[0])
    if companies and len(companies) != len(COMPANY_SPECS):
        raise RuntimeError(
            'O Grupo Inventory histórico deve conter Brasil, Latam e OXXO.'
        )
    Secao.objects.using(using).filter(
        empresa_id__in=[company.pk for company in companies],
        habilitado=True,
    ).update(permite_conteudo_global_legado=True)


class Migration(migrations.Migration):
    dependencies = [('estoque', '0057_modulos_independentes')]

    operations = [
        migrations.AddField(
            model_name='secaodocumentacaoempresa',
            name='permite_conteudo_global_legado',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    'Libera, de forma explícita, o acervo histórico sem empresa proprietária.'
                ),
            ),
        ),
        migrations.RunPython(
            preserve_inventory_legacy_library,
            migrations.RunPython.noop,
        ),
    ]
