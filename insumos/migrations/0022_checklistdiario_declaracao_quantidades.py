from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0021_checklistdiario_logistica'),
    ]

    operations = [
        migrations.AddField(
            model_name='checklistdiario',
            name='declaracao_quantidades',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
