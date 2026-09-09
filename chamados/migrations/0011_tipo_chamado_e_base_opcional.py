from datetime import timedelta

from django.db import migrations, models
import django.db.models.deletion


def normalizar_chamados_existentes(apps, schema_editor):
    Chamado = apps.get_model('chamados', 'Chamado')
    for chamado in Chamado.objects.only('pk', 'aberto_em').iterator():
        Chamado.objects.filter(pk=chamado.pk).update(
            tipo_chamado='OPERACIONAL',
            prazo_sla_em=chamado.aberto_em + timedelta(minutes=30),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('chamados', '0010_alter_chamadoanexo_arquivo'),
    ]

    operations = [
        migrations.AddField(
            model_name='chamado',
            name='tipo_chamado',
            field=models.CharField(
                choices=[
                    ('OPERACIONAL', 'Operacional'),
                    ('REPARACAO', 'Reparação / Manutenção'),
                ],
                db_index=True,
                default='OPERACIONAL',
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name='chamado',
            name='base',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='chamados',
                to='estoque.base',
            ),
        ),
        migrations.RunPython(normalizar_chamados_existentes, migrations.RunPython.noop),
    ]
