from django.db import migrations, models
import django.db.models.deletion


def preencher_base_origem_sick(apps, schema_editor):
    Sick = apps.get_model('estoque', 'Sick')
    for sick in Sick.objects.filter(base_origem__isnull=True).select_related('equipamento'):
        sick.base_origem_id = sick.equipamento.regional_id
        sick.save(update_fields=['base_origem'])


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0032_alter_equipamento_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='emprestimo',
            name='codigo_rastreio_devolucao',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='emprestimo',
            name='codigo_rastreio_envio',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='transferencia',
            name='codigo_rastreio',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='sick',
            name='base_origem',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sicks_originados', to='estoque.base'),
        ),
        migrations.AddField(
            model_name='sick',
            name='codigo_rastreio_envio',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='sick',
            name='codigo_rastreio_retorno',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='sick',
            name='tipo_destino',
            field=models.CharField(blank=True, choices=[('MATRIZ', 'Matriz'), ('TERCEIRIZADA', 'Manutenção terceirizada')], db_index=True, max_length=20),
        ),
        migrations.RunPython(preencher_base_origem_sick, migrations.RunPython.noop),
    ]
