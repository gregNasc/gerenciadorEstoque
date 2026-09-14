import uuid

from django.db import migrations, models
from django.utils.text import slugify


def preencher_slugs(apps, schema_editor):
    Empresa = apps.get_model('estoque', 'Empresa')
    used = set()
    for company in Empresa.objects.using(schema_editor.connection.alias).order_by('pk'):
        base = slugify(company.slug or company.nome) or f'empresa-{uuid.uuid4().hex[:12]}'
        base = base[:220]
        candidate = base
        suffix = 2
        while candidate in used:
            marker = f'-{suffix}'
            candidate = f'{base[:220 - len(marker)]}{marker}'
            suffix += 1
        used.add(candidate)
        if company.slug != candidate:
            Empresa.objects.using(schema_editor.connection.alias).filter(
                pk=company.pk,
            ).update(slug=candidate)


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0050_modulos_por_empresa'),
    ]

    operations = [
        migrations.RunPython(preencher_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='empresa',
            name='slug',
            field=models.SlugField(max_length=220, unique=True),
        ),
    ]
