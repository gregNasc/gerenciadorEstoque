from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0072_equipamento_identificadores_flexiveis'),
    ]

    operations = [
        migrations.AddField(
            model_name='equipamento',
            name='imei_1',
            field=models.CharField(
                blank=True, max_length=15, null=True, unique=True,
            ),
        ),
        migrations.AddField(
            model_name='equipamento',
            name='imei_2',
            field=models.CharField(
                blank=True, max_length=15, null=True, unique=True,
            ),
        ),
    ]
