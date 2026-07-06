from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0028_perfil_bases_checklist'),
    ]

    operations = [
        migrations.AlterField(
            model_name='equipamento',
            name='status',
            field=models.CharField(choices=[('ATIVO', 'Ativo'), ('RESERVADO_TRANSFERENCIA', 'Reservado para Transferencia'), ('EM_TRANSITO', 'Em Transito'), ('MANUTENCAO', 'Manutencao'), ('SICK', 'Sick'), ('EM_USO', 'Em Uso'), ('BAIXA', 'Baixa'), ('INATIVO', 'Inativo')], default='ATIVO', max_length=40),
        ),
    ]
