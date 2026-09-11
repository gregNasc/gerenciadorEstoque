from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0048_produto_categoria_e_origem_empresa'),
    ]

    operations = [
        migrations.AddField(
            model_name='driverimpressora',
            name='empresa',
            field=models.ForeignKey(
                blank=True,
                help_text='Vazio identifica documentação global legada da plataforma.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='drivers_impressora',
                to='estoque.empresa',
            ),
        ),
        migrations.AddField(
            model_name='resolucaodocumento',
            name='empresa',
            field=models.ForeignKey(
                blank=True,
                help_text='Vazio identifica documentação global legada da plataforma.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='resolucoes_documentacao',
                to='estoque.empresa',
            ),
        ),
        migrations.AddField(
            model_name='videodocumentacao',
            name='empresa',
            field=models.ForeignKey(
                blank=True,
                help_text='Vazio identifica documentação global legada da plataforma.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='videos_documentacao',
                to='estoque.empresa',
            ),
        ),
    ]
