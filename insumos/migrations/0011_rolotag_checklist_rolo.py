import django.db.models.deletion
from django.db import migrations, models


def criar_rolos_existentes(apps, schema_editor):
    LoteTag = apps.get_model('insumos', 'LoteTag')
    RoloTag = apps.get_model('insumos', 'RoloTag')

    for lote in LoteTag.objects.all():
        quantidade = lote.quantidade_disponivel or 0
        for codigo in range(1, quantidade + 1):
            RoloTag.objects.get_or_create(
                lote=lote,
                codigo=codigo,
                defaults={
                    'numero_atual': lote.numero_inicial,
                    'status': 'DISPONIVEL',
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0010_alter_lotetag_quantidade_disponivel'),
    ]

    operations = [
        migrations.CreateModel(
            name='RoloTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.PositiveIntegerField()),
                ('numero_atual', models.IntegerField()),
                ('status', models.CharField(choices=[('DISPONIVEL', 'Disponível'), ('EM_USO', 'Em uso'), ('ESGOTADO', 'Esgotado')], default='DISPONIVEL', max_length=20)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('lote', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rolos', to='insumos.lotetag')),
            ],
            options={
                'indexes': [
                    models.Index(fields=['status'], name='insumos_rol_status_f17a57_idx'),
                    models.Index(fields=['lote', 'status'], name='insumos_rol_lote_id_d5c504_idx'),
                ],
                'unique_together': {('lote', 'codigo')},
            },
        ),
        migrations.AddField(
            model_name='checklistlotetag',
            name='rolo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='checklists_utilizados', to='insumos.rolotag'),
        ),
        migrations.RunPython(criar_rolos_existentes, migrations.RunPython.noop),
    ]
