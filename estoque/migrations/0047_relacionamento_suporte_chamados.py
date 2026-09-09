from django.db import migrations, models


def habilitar_suporte_inventory(apps, schema_editor):
    RelacionamentoEmpresa = apps.get_model('estoque', 'RelacionamentoEmpresa')
    RelacionamentoEmpresa.objects.filter(
        empresa_origem__slug='inventory-brasil',
        empresa_destino__slug__in=('inventory-latam', 'oxxo'),
        ativo=True,
    ).update(compartilha_suporte_chamados=True)


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0046_perfil_empresas_acesso_adicional'),
    ]

    operations = [
        migrations.AddField(
            model_name='relacionamentoempresa',
            name='compartilha_suporte_chamados',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    'Permite que usuários do grupo de suporte atendam chamados '
                    'da origem e do destino, sem ampliar outros módulos.'
                ),
            ),
        ),
        migrations.RunPython(
            habilitar_suporte_inventory,
            migrations.RunPython.noop,
        ),
    ]
