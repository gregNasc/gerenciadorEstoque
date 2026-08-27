import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0039_alter_equipamento_options_alter_perfil_options_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VideoDocumentacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=200)),
                ('descricao', models.TextField(blank=True)),
                ('url', models.URLField(max_length=500)),
                ('origem', models.CharField(choices=[('INTERNO', 'Interno'), ('FABRICANTE', 'Fabricante')], max_length=20)),
                ('produto_codigo', models.CharField(blank=True, db_index=True, max_length=50)),
                ('categoria', models.CharField(blank=True, max_length=100)),
                ('tags', models.CharField(blank=True, max_length=500)),
                ('duracao', models.CharField(blank=True, max_length=20)),
                ('publicado_em', models.DateField(blank=True, null=True)),
                ('ativo', models.BooleanField(default=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('criado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='videos_documentacao_criados', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'vídeo de documentação',
                'verbose_name_plural': 'vídeos de documentação',
                'ordering': ['-publicado_em', '-criado_em', 'titulo'],
                'permissions': [('gerenciar_documentacao', 'Pode gerenciar a Central de Documentação')],
            },
        ),
    ]
