from django.db import migrations, models


def normalizar_identificadores_vazios(apps, schema_editor):
    Equipamento = apps.get_model('estoque', 'Equipamento')
    Equipamento.objects.filter(numero_serie='').update(numero_serie=None)
    Equipamento.objects.filter(patrimonio='').update(patrimonio=None)


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0071_eventonotificacaocustodia_entreganotificacaocustodia_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='equipamento',
            name='numero_serie',
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name='equipamento',
            name='patrimonio',
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name='equipamento',
            name='observacao_operacional',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.RunPython(
            normalizar_identificadores_vazios,
            migrations.RunPython.noop,
        ),
    ]
