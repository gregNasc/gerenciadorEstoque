from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0001_initial'),
    ]

    # O modelo já é criado em 0001_initial. A operação duplicada impedia a
    # criação de bancos novos e do banco de testes com DuplicateTable.
    operations = []
