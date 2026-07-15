from decimal import Decimal

import django.core.validators
from django.db import migrations, models
from django.db.models import Q


def definir_minimos_iniciais(apps, schema_editor):
    Insumo = apps.get_model('insumos', 'Insumo')
    Insumo.objects.filter(ativo=True, tipo_controle='QUANTIDADE').update(
        estoque_minimo=Decimal('5.00')
    )
    Insumo.objects.filter(ativo=True).exclude(tipo_controle='QUANTIDADE').update(
        estoque_minimo=Decimal('2.00')
    )


class Migration(migrations.Migration):
    dependencies = [
        ('insumos', '0019_inventario_tempos_operacionais'),
    ]

    operations = [
        migrations.AlterField(
            model_name='insumo',
            name='estoque_minimo',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('2.00'),
                max_digits=4,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0.00')),
                    django.core.validators.MaxValueValidator(Decimal('10.00')),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name='insumo',
            constraint=models.CheckConstraint(
                condition=Q(
                    estoque_minimo__gte=Decimal('0.00'),
                    estoque_minimo__lte=Decimal('10.00'),
                ),
                name='insumo_estoque_minimo_entre_0_e_10',
            ),
        ),
        migrations.RunPython(
            definir_minimos_iniciais,
            migrations.RunPython.noop,
        ),
    ]
