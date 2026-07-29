from django.db import migrations


TAG_DESCRICOES = (
    ('Etiqueta Setor 0001', 'Etiqueta Setor 00001'),
    ('Etiqueta Setor 1000', 'Etiqueta Setor 01000'),
    ('Etiqueta Setor 2000', 'Etiqueta Setor 02000'),
    ('Etiqueta Setor 3000', 'Etiqueta Setor 03000'),
    ('Etiqueta Setor 3500 - Peso Variável', 'Etiqueta Setor 03500 - Peso Variável'),
    ('Etiqueta Setor 4000', 'Etiqueta Setor 04000'),
    ('Etiqueta Setor 5000', 'Etiqueta Setor 05000'),
    ('Etiqueta Setor 6000', 'Etiqueta Setor 06000'),
    ('Etiqueta Setor 7000', 'Etiqueta Setor 07000'),
    ('Etiqueta Setor 8000', 'Etiqueta Setor 08000'),
    ('Etiqueta Setor 9000', 'Etiqueta Setor 09000'),
    ('Etiqueta Setor 10000', 'Etiqueta Setor 10000'),
    ('Etiqueta Setor 11000', 'Etiqueta Setor 11000'),
    ('Etiqueta Setor 12000', 'Etiqueta Setor 12000'),
    ('Etiqueta Setor 13000', 'Etiqueta Setor 13000'),
    ('Etiqueta Setor 14000', 'Etiqueta Setor 14000'),
    ('Etiqueta Setor 15000', 'Etiqueta Setor 15000'),
    ('Etiqueta Setor 16000', 'Etiqueta Setor 16000'),
    ('Etiqueta Setor 17000', 'Etiqueta Setor 17000'),
    ('Etiqueta Setor 18000', 'Etiqueta Setor 18000'),
    ('Etiqueta Setor 19000', 'Etiqueta Setor 19000'),
    ('Etiqueta Setor 20000', 'Etiqueta Setor 20000'),
)


def _migrar_item_checklist(apps, duplicado, canonico):
    ItemChecklist = apps.get_model('insumos', 'ItemChecklist')
    ConsumoInsumo = apps.get_model('insumos', 'ConsumoInsumo')

    for item in ItemChecklist.objects.filter(insumo_id=duplicado.pk).iterator():
        existente = ItemChecklist.objects.filter(
            checklist_id=item.checklist_id,
            insumo_id=canonico.pk,
        ).first()
        if existente is None:
            item.insumo_id = canonico.pk
            item.save(update_fields=['insumo'])
            continue

        ConsumoInsumo.objects.filter(item_checklist_id=item.pk).update(
            item_checklist_id=existente.pk,
            insumo_id=canonico.pk,
        )
        for campo in (
            'quantidade_enviada',
            'quantidade_utilizada',
            'quantidade_retornada',
            'quantidade_perdida',
        ):
            setattr(existente, campo, getattr(existente, campo) + getattr(item, campo))
        if item.status_retorno == 'PENDENTE':
            existente.status_retorno = 'PENDENTE'
        existente.save()
        item.delete()


def _migrar_referencias(apps, duplicado, canonico):
    _migrar_item_checklist(apps, duplicado, canonico)

    for nome_modelo in (
        'MovimentacaoInsumo',
        'ItemSolicitacaoInsumo',
        'PrecoFornecedorInsumo',
        'PesquisaPrecoOnline',
        'OfertaPrecoOnline',
        'ConsumoInsumo',
    ):
        modelo = apps.get_model('insumos', nome_modelo)
        modelo.objects.filter(insumo_id=duplicado.pk).update(insumo_id=canonico.pk)


def consolidar_tags(apps, schema_editor):
    CategoriaInsumo = apps.get_model('insumos', 'CategoriaInsumo')
    Insumo = apps.get_model('insumos', 'Insumo')

    categoria_tags, _ = CategoriaInsumo.objects.get_or_create(nome='TAGS')
    categoria_dp = CategoriaInsumo.objects.filter(nome='DEPARTAMENTO PESSOAL').first()
    categorias_validas = [categoria_tags.pk]
    if categoria_dp is not None:
        categorias_validas.append(categoria_dp.pk)

    for descricao_antiga, descricao_nova in TAG_DESCRICOES:
        candidatos = list(
            Insumo.objects.filter(
                categoria_id__in=categorias_validas,
                descricao__in=(descricao_antiga, descricao_nova),
            ).order_by('pk')
        )
        canonico = next(
            (
                item for item in candidatos
                if item.categoria_id == categoria_tags.pk and item.descricao == descricao_nova
            ),
            None,
        )
        if canonico is None:
            canonico = next(
                (item for item in candidatos if item.categoria_id == categoria_tags.pk),
                None,
            )
        if canonico is None and candidatos:
            canonico = candidatos[0]
        if canonico is None:
            canonico = Insumo.objects.create(
                descricao=descricao_nova,
                categoria_id=categoria_tags.pk,
                unidade_medida='ROLO',
                tipo_controle='LOTE',
                ativo=True,
            )
            candidatos = [canonico]

        for duplicado in candidatos:
            if duplicado.pk == canonico.pk:
                continue
            _migrar_referencias(apps, duplicado, canonico)
            if canonico.preco_referencia_id is None and duplicado.preco_referencia_id:
                canonico.preco_referencia_id = duplicado.preco_referencia_id
            if not canonico.valor_medio and duplicado.valor_medio:
                canonico.valor_medio = duplicado.valor_medio
            canonico.ativo = canonico.ativo or duplicado.ativo
            duplicado.delete()

        canonico.descricao = descricao_nova
        canonico.categoria_id = categoria_tags.pk
        canonico.unidade_medida = 'ROLO'
        canonico.tipo_controle = 'LOTE'
        canonico.save()


def restaurar_descricoes(apps, schema_editor):
    CategoriaInsumo = apps.get_model('insumos', 'CategoriaInsumo')
    Insumo = apps.get_model('insumos', 'Insumo')

    categoria_tags = CategoriaInsumo.objects.filter(nome='TAGS').first()
    if categoria_tags is None:
        return
    for descricao_antiga, descricao_nova in TAG_DESCRICOES:
        Insumo.objects.filter(
            categoria_id=categoria_tags.pk,
            descricao=descricao_nova,
        ).update(descricao=descricao_antiga)


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0023_checklistdiario_declaracao_dados'),
    ]

    operations = [
        migrations.RunPython(consolidar_tags, restaurar_descricoes),
    ]
