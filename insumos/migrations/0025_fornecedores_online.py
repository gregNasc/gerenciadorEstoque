from django.db import migrations, models


FORNECEDORES = (
    {
        'nome': 'Gimba (SupriCorp Suprimentos Ltda)',
        'nomes_alternativos': ('Gimba', 'SupriCorp Suprimentos Ltda'),
        'documento': '54651716001150',
        'site': 'https://www.gimba.com.br/',
        'fonte_online': 'GIMBA',
        'observacao': 'Fornecedor com catálogo online preparado para pesquisa de preços.',
    },
    {
        'nome': 'Fidelity Suprimentos',
        'nomes_alternativos': (
            'Fidelity',
            'Fidelity Comércio de Artigos para Escritório Papelaria Informática Descartável e Higiene Ltda',
        ),
        'documento': '17829173000110',
        'site': 'https://fidelitysuprimentos.com.br/',
        'fonte_online': 'FIDELITY',
        'email': 'contato@fidelitysuprimentos.com.br',
        'telefone': '(11) 2373-5621',
        'observacao': 'Fornecedor com catálogo online preparado para pesquisa de preços.',
    },
)


def cadastrar_fornecedores(apps, schema_editor):
    Fornecedor = apps.get_model('insumos', 'FornecedorInsumo')

    for dados in FORNECEDORES:
        fornecedor = Fornecedor.objects.filter(documento=dados['documento']).first()
        if fornecedor is None:
            for nome in (dados['nome'], *dados['nomes_alternativos']):
                fornecedor = Fornecedor.objects.filter(nome__iexact=nome).first()
                if fornecedor is not None:
                    break

        valores = {
            'documento': dados['documento'],
            'site': dados['site'],
            'fonte_online': dados['fonte_online'],
            'ativo': True,
        }
        for campo in ('email', 'telefone'):
            if dados.get(campo):
                valores[campo] = dados[campo]

        if fornecedor is None:
            Fornecedor.objects.create(
                nome=dados['nome'],
                observacao=dados['observacao'],
                **valores,
            )
            continue

        if not Fornecedor.objects.exclude(pk=fornecedor.pk).filter(nome=dados['nome']).exists():
            fornecedor.nome = dados['nome']
        for campo, valor in valores.items():
            setattr(fornecedor, campo, valor)
        if not fornecedor.observacao:
            fornecedor.observacao = dados['observacao']
        fornecedor.save()


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0024_consolidar_categoria_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='fornecedorinsumo',
            name='fonte_online',
            field=models.CharField(
                blank=True,
                choices=[('GIMBA', 'Gimba'), ('FIDELITY', 'Fidelity Suprimentos')],
                db_index=True,
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name='fornecedorinsumo',
            name='site',
            field=models.URLField(blank=True, max_length=300),
        ),
        migrations.RunPython(cadastrar_fornecedores, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='fornecedorinsumo',
            constraint=models.UniqueConstraint(
                condition=~models.Q(fonte_online=''),
                fields=('fonte_online',),
                name='fornecedor_fonte_online_unica',
            ),
        ),
    ]
