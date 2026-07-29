from django.db import migrations, models


TERMOS_POR_DESCRICAO = {
    'Cabo de Rede (RJ45)': 'cabo de rede RJ45 CAT6',
    'Durex': 'fita adesiva transparente durex',
    'Luva': 'luva descartavel procedimento',
    'Máscara': 'mascara descartavel tripla',
    'Papel Sulfite (Pacote)': 'papel sulfite A4 75g 500 folhas',
    'Touca': 'touca descartavel sanfonada',
}


def configurar_termos(apps, schema_editor):
    Insumo = apps.get_model('insumos', 'Insumo')
    for insumo in Insumo.objects.filter(termo_pesquisa_online='').iterator():
        insumo.termo_pesquisa_online = insumo.descricao
        insumo.save(update_fields=['termo_pesquisa_online'])
    for descricao, termo in TERMOS_POR_DESCRICAO.items():
        Insumo.objects.filter(descricao__iexact=descricao).update(
            termo_pesquisa_online=termo,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0025_fornecedores_online'),
    ]

    operations = [
        migrations.AddField(
            model_name='insumo',
            name='termo_pesquisa_online',
            field=models.CharField(
                blank=True,
                help_text='Termo usado para localizar este insumo nos catálogos dos fornecedores.',
                max_length=255,
            ),
        ),
        migrations.RunPython(configurar_termos, migrations.RunPython.noop),
    ]
