import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0047_relacionamento_suporte_chamados'),
    ]

    operations = [
        migrations.AlterField(
            model_name='produto',
            name='categoria',
            field=models.CharField(db_index=True, max_length=50),
        ),
        migrations.AddField(
            model_name='produto',
            name='empresa_catalogo_origem',
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    'Empresa que originou o item; vazio identifica um item técnico global.'
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='produtos_catalogo_criados',
                to='estoque.empresa',
            ),
        ),
    ]
