from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0018_remove_solicitacao_data_criacao_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notificacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(max_length=20)),
                ('evento', models.CharField(max_length=30)),
                ('mensagem', models.CharField(max_length=255)),
                ('lida', models.BooleanField(default=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('link', models.CharField(max_length=255, null=True, blank=True)),
            ],
        ),
    ]