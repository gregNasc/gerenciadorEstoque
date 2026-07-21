from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0020_limite_estoque_minimo'),
    ]

    operations = [
        migrations.AddField(
            model_name='checklistdiario',
            name='quantidade_volumes',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='checklistdiario',
            name='transporte',
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
