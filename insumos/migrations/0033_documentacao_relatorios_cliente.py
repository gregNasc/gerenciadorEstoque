import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0032_alter_checklistdiario_options_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TipoRelatorioCliente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=120, unique=True)),
                ('descricao', models.TextField(blank=True)),
                ('ativo', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'tipo de relatório de cliente',
                'verbose_name_plural': 'tipos de relatório de cliente',
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='ClienteRelatorio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('obrigatorio', models.BooleanField(default=True)),
                ('observacao', models.TextField(blank=True)),
                ('ordem', models.PositiveIntegerField(default=0)),
                ('ativo', models.BooleanField(default=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relatorios_requeridos', to='insumos.cliente')),
                ('tipo_relatorio', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='insumos.tiporelatoriocliente')),
            ],
            options={
                'verbose_name': 'relatório requerido por cliente',
                'verbose_name_plural': 'relatórios requeridos por cliente',
                'ordering': ['ordem', 'tipo_relatorio__nome'],
                'permissions': [('gerenciar_documentacao', 'Pode gerenciar a documentação de clientes')],
                'constraints': [models.UniqueConstraint(fields=('cliente', 'tipo_relatorio'), name='cliente_tipo_relatorio_unico')],
            },
        ),
    ]
