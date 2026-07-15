from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0018_pesquisaprecoonline_ofertaprecoonline'),
    ]

    operations = [
        migrations.AddField(
            model_name='inventario',
            name='custo_hora_pessoa',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='inventario',
            name='fim_contagem',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='inventario',
            name='fim_previsto',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='inventario',
            name='fim_real',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='inventario',
            name='inicio_contagem',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='inventario',
            name='inicio_previsto',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='inventario',
            name='inicio_real',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='inventario',
            name='total_pecas',
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
    ]
