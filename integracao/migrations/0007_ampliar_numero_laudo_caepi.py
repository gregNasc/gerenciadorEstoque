from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('integracao', '0006_caepi_catalogo_local'),
    ]

    operations = [
        migrations.AlterField(
            model_name='caepiregistro',
            name='numero_laudo',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
