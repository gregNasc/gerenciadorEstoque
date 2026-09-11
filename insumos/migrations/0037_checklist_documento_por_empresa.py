from django.db import migrations, models
import django.db.models.deletion


def identificar_empresa_documento(apps, schema_editor):
    Documento = apps.get_model('insumos', 'ClienteChecklistDocumento')
    Inventario = apps.get_model('insumos', 'Inventario')
    for documento in Documento.objects.filter(empresa__isnull=True).iterator():
        empresas = list(
            Inventario.objects.filter(cliente_id=documento.cliente_id)
            .exclude(base__empresa_id__isnull=True)
            .values_list('base__empresa_id', flat=True)
            .distinct()[:2]
        )
        if len(empresas) == 1:
            Documento.objects.filter(pk=documento.pk, empresa__isnull=True).update(
                empresa_id=empresas[0]
            )


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0049_documentacao_por_empresa'),
        ('insumos', '0036_precos_e_pesquisas_por_empresa'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clientechecklistdocumento',
            name='cliente',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='checklist_documentos',
                to='insumos.cliente',
            ),
        ),
        migrations.AddField(
            model_name='clientechecklistdocumento',
            name='empresa',
            field=models.ForeignKey(
                blank=True,
                help_text='Vazio identifica documento global legado da plataforma.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='checklists_documentacao_clientes',
                to='estoque.empresa',
            ),
        ),
        migrations.RunPython(
            identificar_empresa_documento,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='clientechecklistdocumento',
            constraint=models.UniqueConstraint(
                condition=models.Q(('empresa__isnull', False)),
                fields=('cliente', 'empresa'),
                name='uq_checklist_cliente_empresa',
            ),
        ),
        migrations.AddConstraint(
            model_name='clientechecklistdocumento',
            constraint=models.UniqueConstraint(
                condition=models.Q(('empresa__isnull', True)),
                fields=('cliente',),
                name='uq_checklist_cliente_global',
            ),
        ),
    ]
