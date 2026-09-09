import django.utils.timezone
from django.db import migrations, models
from django.db.models import Count, Q
from django.utils.text import slugify


SLUG_MAX_LENGTH = 220


def _slug_disponivel(nome, empresa_id, usados):
    base = slugify(nome) or f'empresa-{empresa_id}'
    base = base[:SLUG_MAX_LENGTH]
    candidato = base
    sequencia = 2

    while candidato in usados:
        sufixo = f'-{sequencia}'
        candidato = f'{base[:SLUG_MAX_LENGTH - len(sufixo)]}{sufixo}'
        sequencia += 1

    return candidato


def preencher_slugs(apps, schema_editor):
    Empresa = apps.get_model('estoque', 'Empresa')
    usados = set(
        Empresa.objects.exclude(slug__isnull=True)
        .exclude(slug='')
        .values_list('slug', flat=True)
    )

    for empresa in Empresa.objects.order_by('pk').iterator():
        if empresa.slug:
            usados.add(empresa.slug)
            continue

        novo_slug = _slug_disponivel(empresa.nome, empresa.pk, usados)
        Empresa.objects.filter(pk=empresa.pk, slug__isnull=True).update(
            slug=novo_slug,
        )
        usados.add(novo_slug)

    sem_slug = Empresa.objects.filter(Q(slug__isnull=True) | Q(slug='')).exists()
    duplicados = (
        Empresa.objects.values('slug')
        .annotate(total=Count('pk'))
        .filter(total__gt=1)
        .exists()
    )
    if sem_slug or duplicados:
        raise RuntimeError('Não foi possível gerar slugs válidos e únicos para as empresas.')


def limpar_slugs(apps, schema_editor):
    Empresa = apps.get_model('estoque', 'Empresa')
    Empresa.objects.update(slug=None)


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0042_driverimpressora'),
    ]

    operations = [
        migrations.AddField(
            model_name='empresa',
            name='ativa',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='empresa',
            name='atualizado_em',
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='empresa',
            name='criado_em',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='empresa',
            name='slug',
            field=models.SlugField(
                blank=True,
                db_index=True,
                max_length=220,
                null=True,
            ),
        ),
        migrations.RunPython(preencher_slugs, limpar_slugs),
    ]
