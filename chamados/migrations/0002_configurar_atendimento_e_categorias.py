from django.db import migrations


CATEGORIAS = [
    ('FALHA NA IMPRESSÃO', 8),
    ('IMPRESSORA QUEIMADA', 8),
    ('IMPRESSORA NÃO RECONHECE', 8),
    ('ROUTER NÃO FUNCIONA', 4),
    ('NOTEBOOK NÃO LIGA', 8),
    ('COLETOR NÃO CONECTA NA REDE', 4),
    ('COLETOR NÃO TRANSMITE', 4),
    ('OUTRO', 24),
]


def configurar(apps, schema_editor):
    Categoria = apps.get_model('chamados', 'CategoriaChamado')
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')

    for nome, sla_horas in CATEGORIAS:
        Categoria.objects.get_or_create(
            nome=nome,
            defaults={'sla_horas': sla_horas, 'ativo': True},
        )

    grupo, _ = Group.objects.get_or_create(name='CHAMADOS_ATENDIMENTO')
    content_type, _ = ContentType.objects.get_or_create(
        app_label='chamados', model='chamado'
    )
    permissoes = []
    for codename, name in [
        ('atender_chamado', 'Pode atender chamados'),
        ('visualizar_todos_chamados', 'Pode visualizar todos os chamados'),
        ('exportar_chamados', 'Pode exportar chamados'),
    ]:
        permissao, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={'name': name},
        )
        permissoes.append(permissao)
    grupo.permissions.add(*permissoes)


class Migration(migrations.Migration):

    dependencies = [
        ('chamados', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(configurar, migrations.RunPython.noop),
    ]
