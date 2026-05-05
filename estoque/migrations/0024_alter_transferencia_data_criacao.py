from django.db import migrations, models
from django.utils import timezone

def set_default_data(apps, schema_editor):
    Transferencia = apps.get_model('estoque', 'Transferencia')
    Transferencia.objects.filter(data_criacao__isnull=True).update(
        data_criacao=timezone.now()
    )

class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0023_fix_data_criacao_transferencia'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transferencia',
            name='data_criacao',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.RunPython(set_default_data),
        migrations.AlterField(
            model_name='transferencia',
            name='data_criacao',
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]