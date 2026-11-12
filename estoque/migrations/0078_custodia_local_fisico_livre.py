from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0077_custodia_termos_modalidades'),
    ]

    operations = [
        migrations.AddField(
            model_name='custodia',
            name='local_fisico_livre',
            field=models.CharField(
                blank=True,
                default='',
                max_length=200,
                verbose_name='Local físico informado',
            ),
        ),
    ]
