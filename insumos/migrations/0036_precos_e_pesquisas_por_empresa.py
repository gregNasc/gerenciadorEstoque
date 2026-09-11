import django.db.models.deletion
from django.db import migrations, models


def preencher_empresas(apps, schema_editor):
    Perfil = apps.get_model('estoque', 'Perfil')
    Preco = apps.get_model('insumos', 'PrecoFornecedorInsumo')
    Pesquisa = apps.get_model('insumos', 'PesquisaPrecoOnline')

    usuarios = set(
        Preco.objects.exclude(cadastrado_por_id=None).values_list(
            'cadastrado_por_id', flat=True,
        )
    )
    usuarios.update(
        Pesquisa.objects.exclude(pesquisado_por_id=None).values_list(
            'pesquisado_por_id', flat=True,
        )
    )
    empresas_por_usuario = dict(
        Perfil.objects.filter(user_id__in=usuarios).exclude(
            empresa_id=None,
        ).values_list('user_id', 'empresa_id')
    )
    for usuario_id, empresa_id in empresas_por_usuario.items():
        Preco.objects.filter(
            empresa_id=None,
            cadastrado_por_id=usuario_id,
        ).update(empresa_id=empresa_id)
        Pesquisa.objects.filter(
            empresa_id=None,
            pesquisado_por_id=usuario_id,
        ).update(empresa_id=empresa_id)


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0048_produto_categoria_e_origem_empresa'),
        ('insumos', '0035_historicoinsumo_base'),
    ]

    operations = [
        migrations.AddField(
            model_name='precofornecedorinsumo',
            name='empresa',
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    'Empresa proprietária da cotação; vazio identifica legado da plataforma.'
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='precos_fornecedores_insumos',
                to='estoque.empresa',
            ),
        ),
        migrations.AddField(
            model_name='pesquisaprecoonline',
            name='empresa',
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    'Empresa proprietária da pesquisa; vazio identifica legado da plataforma.'
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='pesquisas_preco_online',
                to='estoque.empresa',
            ),
        ),
        migrations.RunPython(preencher_empresas, migrations.RunPython.noop),
    ]
