from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('integracao', '0010_caepi_cursor_arquivo_processamento'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TotvsIntegrationConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('habilitada', models.BooleanField(db_index=True, default=False)),
                ('produto', models.CharField(choices=[('NAO_DEFINIDO', 'Não definido'), ('PROTHEUS', 'Protheus'), ('DATASUL', 'Datasul'), ('RM', 'RM'), ('OUTRO', 'Outro produto TOTVS')], default='NAO_DEFINIDO', max_length=20)),
                ('produto_descricao', models.CharField(blank=True, default='', max_length=120)),
                ('versao', models.CharField(blank=True, default='', max_length=100)),
                ('modulos', models.JSONField(blank=True, default=list)),
                ('ambiente', models.CharField(choices=[('HOMOLOGACAO', 'Homologação'), ('PRODUCAO', 'Produção')], default='HOMOLOGACAO', max_length=20)),
                ('api_base_url', models.URLField(blank=True, default='', max_length=500)),
                ('api_versao', models.CharField(blank=True, default='', max_length=80)),
                ('codigo_empresa', models.CharField(blank=True, default='', max_length=80)),
                ('codigo_filial', models.CharField(blank=True, default='', max_length=80)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('empresa', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='configuracao_totvs', to='estoque.empresa')),
            ],
            options={
                'verbose_name': 'Configuração TOTVS por empresa',
                'verbose_name_plural': 'Configurações TOTVS por empresa',
                'ordering': ('empresa__nome',),
            },
        ),
        migrations.CreateModel(
            name='TotvsOperation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operacao', models.CharField(db_index=True, max_length=80)),
                ('recurso_tipo', models.CharField(max_length=80)),
                ('recurso_id', models.CharField(max_length=100)),
                ('versao_payload', models.PositiveSmallIntegerField(default=1)),
                ('idempotency_key', models.CharField(editable=False, max_length=64, unique=True)),
                ('status', models.CharField(choices=[('AGUARDANDO', 'Aguardando'), ('PROCESSANDO', 'Processando'), ('NOVA_TENTATIVA', 'Nova tentativa agendada'), ('ENVIADA', 'Enviada'), ('CONFIRMADA', 'Confirmada'), ('RECONCILIAR', 'Requer reconciliação'), ('FALHOU', 'Falhou'), ('CANCELADA', 'Cancelada')], db_index=True, default='AGUARDANDO', max_length=20)),
                ('referencia_remota', models.CharField(blank=True, db_index=True, default='', max_length=160)),
                ('status_remoto', models.CharField(blank=True, default='', max_length=100)),
                ('tentativas', models.PositiveIntegerField(default=0)),
                ('proxima_tentativa_em', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('iniciada_em', models.DateTimeField(blank=True, null=True)),
                ('finalizada_em', models.DateTimeField(blank=True, null=True)),
                ('ultimo_erro_codigo', models.CharField(blank=True, default='', max_length=100)),
                ('ultimo_erro_mensagem', models.CharField(blank=True, default='', max_length=255)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('criado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='operacoes_totvs_criadas', to=settings.AUTH_USER_MODEL)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='operacoes_totvs', to='estoque.empresa')),
            ],
            options={
                'verbose_name': 'Operação TOTVS',
                'verbose_name_plural': 'Operações TOTVS',
                'ordering': ('-criado_em', '-id'),
                'indexes': [models.Index(fields=['empresa', 'status'], name='totvs_op_empresa_status_idx'), models.Index(fields=['status', 'proxima_tentativa_em'], name='totvs_op_retry_idx')],
            },
        ),
        migrations.CreateModel(
            name='TotvsOperationAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.PositiveIntegerField()),
                ('resultado', models.CharField(blank=True, default='', max_length=30)),
                ('http_status', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('requisicao_sha256', models.CharField(blank=True, default='', max_length=64)),
                ('resposta_sha256', models.CharField(blank=True, default='', max_length=64)),
                ('erro_codigo', models.CharField(blank=True, default='', max_length=100)),
                ('iniciada_em', models.DateTimeField(auto_now_add=True)),
                ('finalizada_em', models.DateTimeField(blank=True, null=True)),
                ('operacao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historico_tentativas', to='integracao.totvsoperation')),
            ],
            options={
                'verbose_name': 'Tentativa de operação TOTVS',
                'verbose_name_plural': 'Tentativas de operações TOTVS',
                'ordering': ('operacao_id', 'numero'),
                'indexes': [models.Index(fields=['operacao', 'iniciada_em'], name='totvs_try_op_inicio_idx')],
                'constraints': [models.UniqueConstraint(fields=('operacao', 'numero'), name='totvs_tentativa_numero_uq')],
            },
        ),
    ]
