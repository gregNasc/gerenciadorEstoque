import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('integracao', '0005_docusignenvelope_docusignevent_docusigntenantconfig_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CaepiImportacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome_arquivo', models.CharField(max_length=255)),
                ('sha256', models.CharField(db_index=True, max_length=64, unique=True)),
                ('tamanho_bytes', models.PositiveBigIntegerField()),
                ('status', models.CharField(choices=[('PROCESSANDO', 'Processando'), ('PREVIA', 'Prévia pronta'), ('PUBLICADA', 'Publicada'), ('SUBSTITUIDA', 'Substituída'), ('FALHOU', 'Falhou')], db_index=True, default='PROCESSANDO', max_length=16)),
                ('total_registros', models.PositiveIntegerField(default=0)),
                ('novos', models.PositiveIntegerField(default=0)),
                ('alterados', models.PositiveIntegerField(default=0)),
                ('inalterados', models.PositiveIntegerField(default=0)),
                ('rejeitados', models.PositiveIntegerField(default=0)),
                ('advertencias', models.JSONField(blank=True, default=list)),
                ('erro', models.TextField(blank=True, default='')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('finalizado_em', models.DateTimeField(blank=True, null=True)),
                ('publicado_em', models.DateTimeField(blank=True, null=True)),
                ('duracao_ms', models.PositiveBigIntegerField(default=0)),
                ('criado_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='importacoes_caepi', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Importação CAEPI', 'verbose_name_plural': 'Importações CAEPI', 'ordering': ('-criado_em',)},
        ),
        migrations.CreateModel(
            name='CaepiRegistro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_ca', models.CharField(db_index=True, max_length=40)),
                ('validade_ca', models.DateField(blank=True, db_index=True, null=True)),
                ('situacao', models.CharField(blank=True, db_index=True, default='', max_length=80)),
                ('natureza', models.CharField(blank=True, default='', max_length=80)),
                ('equipamento', models.CharField(blank=True, default='', max_length=255)),
                ('descricao_equipamento', models.TextField(blank=True, default='')),
                ('marca', models.CharField(blank=True, default='', max_length=255)),
                ('referencia', models.CharField(blank=True, default='', max_length=255)),
                ('cor', models.CharField(blank=True, default='', max_length=255)),
                ('aprovado_para', models.TextField(blank=True, default='')),
                ('restricao', models.TextField(blank=True, default='')),
                ('observacao_analise', models.TextField(blank=True, default='')),
                ('numero_laudo', models.CharField(blank=True, default='', max_length=120)),
                ('norma', models.TextField(blank=True, default='')),
                ('hash_registro', models.CharField(db_index=True, max_length=64)),
                ('importacao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='registros', to='integracao.caepiimportacao')),
            ],
            options={'verbose_name': 'Registro CAEPI', 'verbose_name_plural': 'Registros CAEPI', 'ordering': ('numero_ca', 'id')},
        ),
        migrations.AddConstraint(
            model_name='caepiimportacao',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'PUBLICADA')), fields=('status',), name='caepi_uma_importacao_publicada'),
        ),
        migrations.AddConstraint(
            model_name='caepiregistro',
            constraint=models.UniqueConstraint(fields=('importacao', 'hash_registro'), name='caepi_registro_hash_importacao_uq'),
        ),
        migrations.AddIndex(
            model_name='caepiregistro',
            index=models.Index(fields=['importacao', 'numero_ca'], name='caepi_import_ca_idx'),
        ),
    ]
