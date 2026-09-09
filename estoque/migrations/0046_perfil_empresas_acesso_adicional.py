from django.db import migrations, models


def _active_destination_ids(Capability, origin_company_id):
    return list(
        Capability.objects.filter(
            relacionamento__empresa_origem_id=origin_company_id,
            relacionamento__ativo=True,
            ativo=True,
        )
        .order_by()
        .values_list('relacionamento__empresa_destino_id', flat=True)
        .distinct()
    )


def preserve_existing_admin_relationship_access(apps, schema_editor):
    Perfil = apps.get_model('estoque', 'Perfil')
    Capability = apps.get_model('estoque', 'CapacidadeRelacionamentoEmpresa')
    through = Perfil.empresas_acesso_adicional.through

    additions = []
    profiles = Perfil.objects.filter(
        role='admin',
        empresa_id__isnull=False,
    ).only('pk', 'empresa_id')
    for profile in profiles.iterator():
        destination_ids = _active_destination_ids(Capability, profile.empresa_id)
        additions.extend(
            through(perfil_id=profile.pk, empresa_id=destination_id)
            for destination_id in destination_ids
            if destination_id != profile.empresa_id
        )

    through.objects.bulk_create(additions, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0045_inventory_brasil_relationships'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfil',
            name='empresas_acesso_adicional',
            field=models.ManyToManyField(
                blank=True,
                related_name='perfis_com_acesso_adicional',
                to='estoque.empresa',
            ),
        ),
        migrations.RunPython(
            preserve_existing_admin_relationship_access,
            migrations.RunPython.noop,
        ),
    ]
