from django.db import migrations, models
from django.db.models import Q


def preencher_status_existente(apps, schema_editor):
    Ativo = apps.get_model('insumos', 'AtivoInsumoIndividualizado')
    Ativo.objects.filter(ativo=True).update(status='OPERACIONAL')
    Ativo.objects.filter(ativo=False).update(status='INATIVO')


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0048_certificado_snapshot_caepi'),
    ]

    operations = [
        migrations.AddField(
            model_name='ativoinsumoindividualizado',
            name='status',
            field=models.CharField(
                choices=[
                    ('OPERACIONAL', 'Operacional'),
                    ('SICK', 'SICK'),
                    ('MANUTENCAO', 'Manutenção'),
                    ('INATIVO', 'Inativo'),
                ],
                db_index=True,
                default='OPERACIONAL',
                max_length=20,
            ),
        ),
        migrations.RunPython(
            preencher_status_existente,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='ativoinsumoindividualizado',
            constraint=models.CheckConstraint(
                condition=Q(status__in=(
                    'OPERACIONAL', 'SICK', 'MANUTENCAO', 'INATIVO',
                )),
                name='insumo_ativo_status_valido',
            ),
        ),
    ]
