from django.db import migrations


def restringir_manutencao_matriz(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model('auth', 'User')
    grupo, _ = Group.objects.get_or_create(name='SICK_MANUTENCAO')
    # Os usernames sao usados somente neste backfill controlado. Em runtime,
    # a autorizacao depende exclusivamente da associacao ao grupo.
    tecnicos = User.objects.filter(
        username__in=['rafael.ribeiro', 'jose.barboza'],
        is_active=True,
    )
    grupo.user_set.set(tecnicos)


def reverter_restricao(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model('auth', 'User')
    grupo = Group.objects.filter(name='SICK_MANUTENCAO').first()
    if grupo:
        grupo.user_set.set(User.objects.filter(username='rafael.ribeiro', is_active=True))


class Migration(migrations.Migration):
    dependencies = [
        ('estoque', '0035_equipamento_condicao_valor_and_more'),
    ]

    operations = [
        migrations.RunPython(restringir_manutencao_matriz, reverter_restricao),
    ]
