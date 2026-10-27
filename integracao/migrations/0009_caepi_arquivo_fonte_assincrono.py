import integracao.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('integracao', '0008_caepi_progresso_recuperacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='caepiimportacao',
            name='arquivo_fonte',
            field=models.FileField(
                blank=True,
                editable=False,
                storage=integracao.models.caepi_source_storage,
                upload_to=integracao.models.caepi_source_upload_to,
            ),
        ),
    ]
