from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0009_alter_checklistlotetag_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lotetag',
            name='quantidade_disponivel',
            field=models.IntegerField(default=0),
        ),
    ]
