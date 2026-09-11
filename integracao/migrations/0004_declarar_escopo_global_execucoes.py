from django.db import migrations


GLOBAL_SCOPE = {
    "kind": "PLATFORM_GLOBAL",
    "source": "INVENTORY_PLANNING",
}


def declarar_escopo_global(apps, schema_editor):
    SyncRun = apps.get_model("integracao", "InventoryPlanningSyncRun")
    for run in SyncRun.objects.all().only("pk", "scope").iterator():
        scope = run.scope if isinstance(run.scope, dict) else {}
        if scope.get("kind") and scope.get("source"):
            continue
        # Os registros deste model são sempre snapshots globais do Planning.
        # Preserve filtros legados, mas não permita que chaves parciais antigas
        # sobrescrevam a declaração canônica da integração.
        SyncRun.objects.filter(pk=run.pk).update(scope={**scope, **GLOBAL_SCOPE})


class Migration(migrations.Migration):

    dependencies = [
        ("integracao", "0003_planningclientbinding_is_active_and_more"),
    ]

    operations = [
        migrations.RunPython(
            declarar_escopo_global,
            migrations.RunPython.noop,
        ),
    ]
