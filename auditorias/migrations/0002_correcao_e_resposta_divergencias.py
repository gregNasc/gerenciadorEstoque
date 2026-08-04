from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('auditorias', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='auditoriabase',
            name='correcao_solicitada_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='auditoriabase',
            name='correcao_solicitada_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='correcoes_auditoria_solicitadas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='auditoriabase',
            name='orientacoes_correcao',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='auditoriabase',
            name='prazo_correcao_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='auditoriadivergencia',
            name='justificativa_base',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='auditoriadivergencia',
            name='respondida_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='auditoriadivergencia',
            name='respondida_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='divergencias_auditoria_respondidas',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
