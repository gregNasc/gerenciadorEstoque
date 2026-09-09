import django.db.models.deletion
from django.db import migrations, models


def preencher_base_historicos(apps, schema_editor):
    Base = apps.get_model('estoque', 'Base')
    ChecklistDiario = apps.get_model('insumos', 'ChecklistDiario')
    HistoricoInsumo = apps.get_model('insumos', 'HistoricoInsumo')
    alias = schema_editor.connection.alias

    bases_por_nome = {}
    for base_id, nome in Base.objects.using(alias).values_list('pk', 'nome'):
        bases_por_nome.setdefault(str(nome).strip().casefold(), []).append(base_id)

    historicos = HistoricoInsumo.objects.using(alias).filter(base__isnull=True)
    for historico in historicos.iterator():
        dados = historico.dados if isinstance(historico.dados, dict) else {}
        base_id = str(dados.get('base_id') or '').strip()
        checklist_id = str(dados.get('checklist') or '').strip()
        if base_id.isdigit() and Base.objects.using(alias).filter(pk=base_id).exists():
            historico.base_id = int(base_id)
        elif checklist_id.isdigit():
            historico.base_id = ChecklistDiario.objects.using(alias).filter(
                pk=checklist_id
            ).values_list('inventario__base_id', flat=True).first()
        else:
            nome = dados.get('base_nome') or dados.get('base')
            candidatos = bases_por_nome.get(str(nome or '').strip().casefold(), [])
            if len(candidatos) == 1:
                historico.base_id = candidatos[0]
        if historico.base_id:
            historico.save(using=alias, update_fields=['base'])


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0047_relacionamento_suporte_chamados'),
        ('insumos', '0034_clientechecklistdocumento'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicoinsumo',
            name='base',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='historicos_insumos',
                to='estoque.base',
            ),
        ),
        migrations.AddIndex(
            model_name='historicoinsumo',
            index=models.Index(
                fields=['base'],
                name='insumos_his_base_id_6aa16b_idx',
            ),
        ),
        migrations.RunPython(
            preencher_base_historicos,
            migrations.RunPython.noop,
        ),
    ]
