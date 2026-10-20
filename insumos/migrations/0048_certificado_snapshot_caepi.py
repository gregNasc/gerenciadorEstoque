import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('integracao', '0006_caepi_catalogo_local'),
        ('insumos', '0047_movimentacao_metadados_epi_patrimonio'),
    ]

    operations = [
        migrations.AddField(
            model_name='insumo',
            name='imagem_principal',
            field=models.ImageField(blank=True, null=True, upload_to='insumos/catalogo/', validators=[django.core.validators.FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])]),
        ),
        migrations.AddField(
            model_name='certificadoepi',
            name='consultado_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='certificadoepi',
            name='importacao_caepi',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='certificados_vinculados', to='integracao.caepiimportacao'),
        ),
        migrations.AddField(
            model_name='certificadoepi',
            name='situacao_oficial',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='certificadoepi',
            name='snapshot_oficial',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
