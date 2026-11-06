from django.db import migrations


def definir_espanhol_para_inventory_latam(apps, schema_editor):
    Perfil = apps.get_model('estoque', 'Perfil')
    Perfil.objects.filter(
        empresa__slug='inventory-latam',
    ).exclude(idioma='es').update(idioma='es')


class Migration(migrations.Migration):
    dependencies = [
        ('estoque', '0074_sick_alvo_generico_r5'),
    ]

    operations = [
        migrations.RunPython(
            definir_espanhol_para_inventory_latam,
            migrations.RunPython.noop,
        ),
    ]
