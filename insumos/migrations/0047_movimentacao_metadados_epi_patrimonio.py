from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0046_padronizar_nome_botas'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimentacaoinsumo',
            name='ativo_individualizado',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='movimentacoes', to='insumos.ativoinsumoindividualizado'),
        ),
        migrations.AddField(
            model_name='movimentacaoinsumo',
            name='lote_epi',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='movimentacoes', to='insumos.loteepi'),
        ),
    ]
