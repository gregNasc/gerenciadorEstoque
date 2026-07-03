from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0012_alteracaocalendario'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inventario',
            name='data_inicio',
            field=models.DateField(db_index=True),
        ),
        migrations.AddIndex(
            model_name='inventario',
            index=models.Index(fields=['base', 'data_inicio'], name='insumos_inv_base_da_6b2e3f_idx'),
        ),
        migrations.AddIndex(
            model_name='inventario',
            index=models.Index(fields=['status', 'data_inicio'], name='insumos_inv_status__25ed2c_idx'),
        ),
    ]
