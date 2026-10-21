from django.db import migrations, models
import django.utils.timezone


def marcar_processamentos_anteriores_como_interrompidos(apps, schema_editor):
    Importacao = apps.get_model('integracao', 'CaepiImportacao')
    Importacao.objects.filter(status='PROCESSANDO').update(
        status='INTERROMPIDA',
        erro=(
            'A execução anterior foi interrompida antes da conclusão. '
            'Reenvie o mesmo arquivo para processá-lo novamente.'
        ),
        finalizado_em=django.utils.timezone.now(),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('integracao', '0007_ampliar_numero_laudo_caepi'),
    ]

    operations = [
        migrations.AddField(
            model_name='caepiimportacao',
            name='atualizado_em',
            field=models.DateTimeField(
                auto_now=True,
                db_index=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='caepiimportacao',
            name='processados',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='caepiimportacao',
            name='status',
            field=models.CharField(
                choices=[
                    ('PROCESSANDO', 'Processando'),
                    ('PREVIA', 'Prévia pronta'),
                    ('PUBLICADA', 'Publicada'),
                    ('SUBSTITUIDA', 'Substituída'),
                    ('FALHOU', 'Falhou'),
                    ('INTERROMPIDA', 'Interrompida'),
                ],
                db_index=True,
                default='PROCESSANDO',
                max_length=16,
            ),
        ),
        migrations.RunPython(
            marcar_processamentos_anteriores_como_interrompidos,
            migrations.RunPython.noop,
        ),
    ]
