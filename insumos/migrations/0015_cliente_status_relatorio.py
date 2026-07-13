from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0014_checklist_retorno_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='status_relatorio',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
