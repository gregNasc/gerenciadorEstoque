from django.db import migrations, models
from django.db.models.functions import Lower
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0071_eventonotificacaocustodia_entreganotificacaocustodia_and_more'),
        ('insumos', '0043_itemchecklist_metadados_epi_snapshot'),
    ]

    operations = [
        migrations.CreateModel(
            name='AtivoInsumoIndividualizado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('patrimonio', models.CharField(db_index=True, max_length=100)),
                ('observacao', models.TextField(blank=True)),
                ('ativo', models.BooleanField(db_index=True, default=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('base', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='ativos_insumos_individualizados', to='estoque.base')),
                ('insumo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='ativos_individualizados', to='insumos.insumo')),
            ],
            options={
                'verbose_name': 'ativo de insumo individualizado',
                'verbose_name_plural': 'ativos de insumos individualizados',
                'ordering': ('base__empresa__nome', 'base__nome', 'insumo__descricao', 'patrimonio'),
            },
        ),
        migrations.AddConstraint(
            model_name='ativoinsumoindividualizado',
            constraint=models.UniqueConstraint(Lower('patrimonio'), name='insumo_ativo_patrimonio_ci_uq'),
        ),
        migrations.AddConstraint(
            model_name='ativoinsumoindividualizado',
            constraint=models.CheckConstraint(condition=~models.Q(patrimonio=''), name='insumo_ativo_patrimonio_nao_vazio'),
        ),
    ]
