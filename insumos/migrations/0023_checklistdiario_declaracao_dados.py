from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0022_checklistdiario_declaracao_quantidades'),
    ]

    operations = [
        migrations.AddField(
            model_name='checklistdiario',
            name='declaracao_dados',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
