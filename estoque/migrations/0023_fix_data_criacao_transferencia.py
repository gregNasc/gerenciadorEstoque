from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0022_notificacao_usuario_alter_notificacao_evento_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='transferencia',
            name='data_criacao',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
    ]