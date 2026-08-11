import chamados.models
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def migrar_status_e_grupos(apps, schema_editor):
    Chamado = apps.get_model('chamados', 'Chamado')
    Chamado.objects.filter(status='ABERTO').update(status='AGUARDANDO_ATENDIMENTO')
    Chamado.objects.filter(status='AGUARDANDO_USUARIO').update(status='AGUARDANDO_SOLICITANTE')
    Chamado.objects.filter(status='FECHADO').update(status='ENCERRADO')

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    content_type, _ = ContentType.objects.get_or_create(app_label='chamados', model='chamado')
    nomes = {
        'atender_chamado': 'Pode atender chamados',
        'visualizar_todos_chamados': 'Pode visualizar todos os chamados',
        'exportar_chamados': 'Pode exportar chamados',
        'supervisionar_chamado': 'Pode supervisionar chamados',
        'visualizar_dashboard_chamado': 'Pode visualizar dashboard de chamados',
        'configurar_chamado': 'Pode configurar chamados e vínculos',
        'converter_chamado_sick': 'Pode converter chamado em SICK',
    }
    permissoes = {}
    for codigo, nome in nomes.items():
        permissoes[codigo], _ = Permission.objects.get_or_create(
            content_type=content_type, codename=codigo, defaults={'name': nome},
        )
    configuracao = {
        'CHAMADOS_SUPORTE': ['atender_chamado', 'visualizar_todos_chamados'],
        'CHAMADOS_SUPERVISOR': list(nomes),
        'CHAMADOS_DASHBOARD': ['visualizar_dashboard_chamado', 'exportar_chamados'],
        'CHAMADOS_CONFIGURACAO': ['configurar_chamado'],
    }
    for grupo_nome, codigos in configuracao.items():
        grupo, _ = Group.objects.get_or_create(name=grupo_nome)
        grupo.permissions.add(*(permissoes[codigo] for codigo in codigos))
    legado = Group.objects.filter(name='CHAMADOS_ATENDIMENTO').first()
    suporte = Group.objects.get(name='CHAMADOS_SUPORTE')
    if legado:
        suporte.user_set.add(*legado.user_set.all())


class Migration(migrations.Migration):

    dependencies = [
        ('chamados', '0002_configurar_atendimento_e_categorias'),
        ('estoque', '0037_whatsapp_consentimento_e_resposta'),
        ('insumos', '0031_inventario_lider_usuario'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='chamado',
            options={
                'ordering': ['-aberto_em', '-id'],
                'permissions': [
                    ('atender_chamado', 'Pode atender chamados'),
                    ('visualizar_todos_chamados', 'Pode visualizar todos os chamados'),
                    ('exportar_chamados', 'Pode exportar chamados'),
                    ('supervisionar_chamado', 'Pode supervisionar chamados'),
                    ('visualizar_dashboard_chamado', 'Pode visualizar dashboard de chamados'),
                    ('configurar_chamado', 'Pode configurar chamados e vínculos'),
                    ('converter_chamado_sick', 'Pode converter chamado em SICK'),
                ],
            },
        ),
        migrations.AddField(
            model_name='chamado', name='aceito_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chamado', name='causa_raiz',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='chamado', name='equipamento',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='chamados', to='estoque.equipamento',
            ),
        ),
        migrations.AddField(
            model_name='chamado', name='primeira_resposta_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chamado', name='sick',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='chamados_origem', to='estoque.sick',
            ),
        ),
        migrations.AlterField(
            model_name='chamado', name='inventario',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='chamados', to='insumos.inventario',
            ),
        ),
        migrations.AlterField(
            model_name='chamado', name='status',
            field=models.CharField(
                choices=[
                    ('ABERTO', 'Aberto'),
                    ('AGUARDANDO_ATENDIMENTO', 'Aguardando atendimento'),
                    ('EM_ATENDIMENTO', 'Em atendimento'),
                    ('AGUARDANDO_SOLICITANTE', 'Aguardando solicitante'),
                    ('AGUARDANDO_TERCEIRO', 'Aguardando terceiro'),
                    ('RESOLVIDO', 'Resolvido'),
                    ('AVALIACAO', 'Aguardando avaliação'),
                    ('ENCERRADO', 'Encerrado'),
                    ('REABERTO', 'Reaberto'),
                    ('CANCELADO', 'Cancelado'),
                ],
                db_index=True, default='ABERTO', max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name='chamadoanexo', name='arquivo',
            field=models.FileField(
                upload_to=chamados.models.caminho_anexo,
                validators=[
                    django.core.validators.FileExtensionValidator(
                        ['pdf', 'png', 'jpg', 'jpeg', 'webp', 'txt', 'csv', 'xlsx', 'docx']
                    ),
                    chamados.models.validar_tamanho_anexo,
                    chamados.models.validar_mime_anexo,
                ],
            ),
        ),
        migrations.CreateModel(
            name='AliasUsuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alias', models.CharField(max_length=150)),
                ('alias_normalizado', models.CharField(editable=False, max_length=150, unique=True)),
                ('ativo', models.BooleanField(default=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aliases_chamados', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['alias_normalizado']},
        ),
        migrations.CreateModel(
            name='ChamadoAvaliacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nota', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('resolvido', models.BooleanField()),
                ('comentario', models.TextField(blank=True)),
                ('criada_em', models.DateTimeField(auto_now_add=True)),
                ('atualizada_em', models.DateTimeField(auto_now=True)),
                ('chamado', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='avaliacao', to='chamados.chamado')),
                ('solicitante', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='avaliacoes_chamados', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ChamadoTransferenciaAtendente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('motivo', models.TextField()),
                ('transferido_em', models.DateTimeField(auto_now_add=True)),
                ('atendente_anterior', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('atendente_novo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('chamado', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transferencias_atendente', to='chamados.chamado')),
                ('transferido_por', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transferencias_chamado_realizadas', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='InventarioLiderHistorico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('texto_original', models.CharField(blank=True, max_length=150)),
                ('justificativa', models.TextField()),
                ('alterado_em', models.DateTimeField(auto_now_add=True)),
                ('alterado_por', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='vinculos_lider_alterados', to=settings.AUTH_USER_MODEL)),
                ('inventario', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='historico_vinculos_lider', to='insumos.inventario')),
                ('lider_anterior', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('lider_novo', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-alterado_em', '-id']},
        ),
        migrations.CreateModel(
            name='PendenciaVinculoLider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('texto_importado', models.CharField(max_length=150)),
                ('texto_normalizado', models.CharField(db_index=True, max_length=150)),
                ('status', models.CharField(choices=[('PENDENTE', 'Pendente'), ('RESOLVIDA', 'Resolvida'), ('DESCARTADA', 'Descartada')], default='PENDENTE', max_length=20)),
                ('resolvida_em', models.DateTimeField(blank=True, null=True)),
                ('justificativa', models.TextField(blank=True)),
                ('criada_em', models.DateTimeField(auto_now_add=True)),
                ('inventario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='pendencia_lider', to='insumos.inventario')),
                ('resolvida_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='pendencias_lider_resolvidas', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ChamadoSessaoAtendimento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('iniciada_em', models.DateTimeField(default=django.utils.timezone.now)),
                ('encerrada_em', models.DateTimeField(blank=True, null=True)),
                ('motivo_encerramento', models.CharField(blank=True, max_length=40)),
                ('atendente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sessoes_chamados', to=settings.AUTH_USER_MODEL)),
                ('chamado', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sessoes', to='chamados.chamado')),
                ('encerrada_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['iniciada_em', 'id'],
                'constraints': [
                    models.UniqueConstraint(
                        condition=models.Q(encerrada_em__isnull=True),
                        fields=('chamado',), name='chamado_uma_sessao_aberta',
                    ),
                ],
            },
        ),
        migrations.RunPython(migrar_status_e_grupos, migrations.RunPython.noop),
    ]
