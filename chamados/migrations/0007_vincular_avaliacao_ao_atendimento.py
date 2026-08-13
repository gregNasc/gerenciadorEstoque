from django.db import migrations, models
import django.db.models.deletion


def vincular_avaliacoes_existentes(apps, schema_editor):
    Avaliacao = apps.get_model('chamados', 'ChamadoAvaliacao')
    Sessao = apps.get_model('chamados', 'ChamadoSessaoAtendimento')

    for avaliacao in Avaliacao.objects.filter(atendimento__isnull=True).iterator():
        atendimento = Sessao.objects.filter(
            chamado_id=avaliacao.chamado_id,
            motivo_encerramento='RESOLVIDO',
        ).order_by('-encerrada_em', '-id').first()
        if atendimento is None:
            atendimento = Sessao.objects.filter(
                chamado_id=avaliacao.chamado_id,
            ).order_by('-encerrada_em', '-id').first()
        if atendimento is not None:
            avaliacao.atendimento_id = atendimento.pk
            avaliacao.save(update_fields=['atendimento'])


class Migration(migrations.Migration):

    dependencies = [
        ('chamados', '0006_chamado_momento_inventario_abertura_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chamadoavaliacao',
            name='chamado',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='avaliacoes',
                to='chamados.chamado',
            ),
        ),
        migrations.AddField(
            model_name='chamadoavaliacao',
            name='atendimento',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='avaliacao',
                to='chamados.chamadosessaoatendimento',
            ),
        ),
        migrations.RunPython(
            vincular_avaliacoes_existentes,
            migrations.RunPython.noop,
        ),
    ]
