import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def preencher_catalogos_existentes(apps, schema_editor):
    Catalogo = apps.get_model('compras', 'CatalogoProdutoEmpresa')
    CodigoCatalogo = apps.get_model('compras', 'CodigoCatalogo')
    ItemAquisicao = apps.get_model('compras', 'ItemAquisicao')
    Equipamento = apps.get_model('estoque', 'Equipamento')
    Produto = apps.get_model('estoque', 'Produto')
    Perfil = apps.get_model('estoque', 'Perfil')

    pares = set(
        Equipamento.objects.exclude(produto_id=None).values_list(
            'regional__empresa_id', 'produto_id'
        )
    )
    pares.update(
        ItemAquisicao.objects.exclude(produto_id=None).values_list(
            'aquisicao__empresa_id', 'produto_id'
        )
    )
    pares.update(
        CodigoCatalogo.objects.exclude(produto_id=None).values_list(
            'empresa_id', 'produto_id'
        )
    )
    produtos = Produto.objects.in_bulk({produto_id for _, produto_id in pares})
    Catalogo.objects.bulk_create(
        [
            Catalogo(
                empresa_id=empresa_id,
                produto_id=produto_id,
                ativo=True,
                preco_referencia=produtos[produto_id].preco_referencia,
                preco_origem=produtos[produto_id].preco_origem,
                preco_fonte=produtos[produto_id].preco_fonte,
                preco_fornecedor_id=produtos[produto_id].preco_fornecedor_id,
                preco_validado_por_id=produtos[produto_id].preco_validado_por_id,
                preco_validado_em=produtos[produto_id].preco_validado_em,
            )
            for empresa_id, produto_id in pares
            if empresa_id and produto_id and produto_id in produtos
        ],
        ignore_conflicts=True,
    )

    empresas_por_produto = {}
    for empresa_id, produto_id in pares:
        if empresa_id and produto_id:
            empresas_por_produto.setdefault(produto_id, set()).add(empresa_id)
    produtos_sem_par = Produto.objects.exclude(
        pk__in=empresas_por_produto,
    ).exclude(criado_por_id=None)
    empresa_por_usuario = dict(
        Perfil.objects.filter(
            user_id__in=produtos_sem_par.values_list('criado_por_id', flat=True),
        ).exclude(empresa_id=None).values_list('user_id', 'empresa_id')
    )
    for produto in Produto.objects.only('pk', 'criado_por_id').iterator():
        empresas = empresas_por_produto.get(produto.pk, set())
        empresa_id = (
            next(iter(empresas))
            if len(empresas) == 1
            else empresa_por_usuario.get(produto.criado_por_id) if not empresas else None
        )
        if empresa_id:
            Produto.objects.filter(pk=produto.pk).update(
                empresa_catalogo_origem_id=empresa_id,
            )

    mapa_origem = {'LEGADO': 'LEGADO_SEM_DOCUMENTO'}
    for catalogo in Catalogo.objects.exclude(preco_referencia=None).iterator():
        Equipamento.objects.filter(
            regional__empresa_id=catalogo.empresa_id,
            produto_id=catalogo.produto_id,
            preco_referencia=None,
        ).update(
            preco_referencia=catalogo.preco_referencia,
            origem_valor=mapa_origem.get(
                catalogo.preco_origem,
                catalogo.preco_origem,
            ),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('compras', '0002_historicoprecoproduto'),
        ('estoque', '0048_produto_categoria_e_origem_empresa'),
        ('insumos', '0035_historicoinsumo_base'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CatalogoProdutoEmpresa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ativo', models.BooleanField(db_index=True, default=True)),
                ('preco_referencia', models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
                ('preco_origem', models.CharField(db_index=True, default='SEM_PRECO_VALIDADO', max_length=30)),
                ('preco_fonte', models.CharField(blank=True, max_length=255)),
                ('preco_validado_em', models.DateTimeField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('configurado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='catalogos_produto_configurados', to=settings.AUTH_USER_MODEL)),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='catalogo_produtos', to='estoque.empresa')),
                ('preco_fornecedor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='catalogos_empresa_precificados', to='insumos.fornecedorinsumo')),
                ('preco_validado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='catalogos_empresa_precos_validados', to=settings.AUTH_USER_MODEL)),
                ('produto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='catalogos_empresa', to='estoque.produto')),
            ],
            options={
                'ordering': ['empresa__nome', 'produto__categoria', 'produto__descricao'],
            },
        ),
        migrations.AddConstraint(
            model_name='catalogoprodutoempresa',
            constraint=models.UniqueConstraint(fields=('empresa', 'produto'), name='catalogo_produto_empresa_unico'),
        ),
        migrations.AddField(
            model_name='historicoprecoproduto',
            name='empresa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='historicos_preco_produto', to='estoque.empresa'),
        ),
        migrations.RunPython(preencher_catalogos_existentes, migrations.RunPython.noop),
    ]
