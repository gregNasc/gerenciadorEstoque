from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0006_alter_transferencia_status'),
    ]

    # As duas FKs já fazem parte de 0001_initial. Mantida como marco da
    # sequência, sem repetir alterações de schema em bancos novos.
    operations = []
