import integracao.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('integracao', '0009_caepi_arquivo_fonte_assincrono'),
    ]

    operations = [
        migrations.AddField(
            model_name='caepiimportacao',
            name='arquivo_processamento',
            field=models.FileField(
                blank=True,
                editable=False,
                storage=integracao.models.caepi_source_storage,
                upload_to=integracao.models.caepi_processing_upload_to,
            ),
        ),
        migrations.AddField(
            model_name='caepiimportacao',
            name='cursor_processamento',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='caepiimportacao',
            name='total_linhas_fonte',
            field=models.PositiveBigIntegerField(default=0),
        ),
    ]
