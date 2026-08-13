from django.db import migrations, models
import django.db.models.deletion


def garantir_vinculo_atendimento(apps, schema_editor):
    Avaliacao = apps.get_model('chamados', 'ChamadoAvaliacao')
    Chamado = apps.get_model('chamados', 'Chamado')
    Sessao = apps.get_model('chamados', 'ChamadoSessaoAtendimento')

    pendentes = []
    for avaliacao in Avaliacao.objects.filter(atendimento__isnull=True).iterator():
        chamado = Chamado.objects.filter(pk=avaliacao.chamado_id).first()
        if chamado is None or chamado.atendente_id is None:
            pendentes.append(avaliacao.pk)
            continue
        inicio = chamado.iniciado_em or chamado.aberto_em
        fim = chamado.resolvido_em or chamado.fechado_em or chamado.atualizado_em
        if fim < inicio:
            fim = inicio
        atendimento = Sessao.objects.create(
            chamado_id=chamado.pk,
            atendente_id=chamado.atendente_id,
            iniciada_em=inicio,
            encerrada_em=fim,
            motivo_encerramento='RESOLVIDO',
            encerrada_por_id=chamado.atendente_id,
        )
        avaliacao.atendimento_id = atendimento.pk
        avaliacao.save(update_fields=['atendimento'])

    if pendentes:
        raise RuntimeError(
            'AVALIAÇÕES SEM ATENDIMENTO OU ATENDENTE: '
            + ', '.join(str(pk) for pk in pendentes)
        )


class Migration(migrations.Migration):

    dependencies = [
        ('chamados', '0007_vincular_avaliacao_ao_atendimento'),
    ]

    operations = [
        migrations.RunPython(
            garantir_vinculo_atendimento,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='chamadoavaliacao',
            name='atendimento',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='avaliacao',
                to='chamados.chamadosessaoatendimento',
            ),
        ),
    ]
