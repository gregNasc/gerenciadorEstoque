from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0036_restringir_manutencao_matriz'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfil',
            name='whatsapp_revogado_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='comunicadoentrega',
            name='provider_resposta',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
