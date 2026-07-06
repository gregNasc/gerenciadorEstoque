import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('insumos', '0013_index_inventario_data_inicio'),
    ]

    operations = [
        migrations.AddField(
            model_name='itemchecklist',
            name='status_retorno',
            field=models.CharField(
                choices=[
                    ('PENDENTE', 'Pendente'),
                    ('CONFERIDO', 'Conferido'),
                ],
                default='PENDENTE',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='checklistequipamento',
            name='motivo_observacao',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='checklistequipamento',
            name='resolvido_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='checklistequipamento',
            name='resolvido_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='checklist_equipamentos_resolvidos',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='checklistequipamento',
            name='status_retorno',
            field=models.CharField(
                choices=[
                    ('PENDENTE', 'Pendente'),
                    ('RETORNADO', 'Retornado'),
                    ('SICK', 'SICK'),
                    ('DANO', 'Dano'),
                    ('PERDA', 'Perda'),
                    ('ROUBO', 'Roubo'),
                ],
                default='PENDENTE',
                max_length=20,
            ),
        ),
    ]
