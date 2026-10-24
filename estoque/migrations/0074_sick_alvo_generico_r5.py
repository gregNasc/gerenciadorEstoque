from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0073_equipamento_imeis'),
        ('insumos', '0049_status_ativo_individualizado_r5'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sick',
            name='equipamento',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sicks',
                to='estoque.equipamento',
            ),
        ),
        migrations.AddField(
            model_name='sick',
            name='ativo_insumo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sicks',
                to='insumos.ativoinsumoindividualizado',
            ),
        ),
        migrations.AddConstraint(
            model_name='sick',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(equipamento__isnull=False, ativo_insumo__isnull=True)
                    | models.Q(equipamento__isnull=True, ativo_insumo__isnull=False)
                ),
                name='sick_exatamente_um_alvo',
            ),
        ),
        migrations.AddConstraint(
            model_name='sick',
            constraint=models.UniqueConstraint(
                fields=('ativo_insumo',),
                condition=models.Q(ativo=True, ativo_insumo__isnull=False),
                name='sick_ativo_insumo_aberto_uq',
            ),
        ),
    ]
