import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0026_alter_equipamento_status'),
        ('insumos', '0011_rolotag_checklist_rolo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AlteracaoCalendario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('revisao', models.IntegerField(blank=True, null=True)),
                ('data', models.DateField(blank=True, null=True)),
                ('cliente_sigla', models.CharField(db_index=True, max_length=20)),
                ('loja', models.CharField(db_index=True, max_length=50)),
                ('descricao', models.TextField(blank=True)),
                ('regional_nome', models.CharField(blank=True, max_length=100)),
                ('solicitante', models.CharField(blank=True, max_length=100)),
                ('observacao', models.TextField(blank=True)),
                ('origem_bloco', models.CharField(choices=[('ATUAL', 'Atual'), ('HISTORICO', 'Historico')], default='ATUAL', max_length=20)),
                ('arquivo', models.CharField(blank=True, max_length=255)),
                ('importado_em', models.DateTimeField(auto_now=True)),
                ('base', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='alteracoes_calendario', to='estoque.base')),
                ('cliente', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='alteracoes_calendario', to='insumos.cliente')),
                ('importado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='alteracoes_calendario_importadas', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Alteracao do calendario',
                'verbose_name_plural': 'Alteracoes do calendario',
                'indexes': [
                    models.Index(fields=['data'], name='insumos_alt_data_b19931_idx'),
                    models.Index(fields=['cliente_sigla', 'loja'], name='insumos_alt_cliente_163588_idx'),
                    models.Index(fields=['origem_bloco', 'revisao'], name='insumos_alt_origem__a44284_idx'),
                    models.Index(fields=['base', 'data'], name='insumos_alt_base_id_1b3c50_idx'),
                ],
            },
        ),
    ]
