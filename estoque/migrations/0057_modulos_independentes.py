from django.db import migrations, models


NEW_MODULES = (
    ('auditorias', 'Auditorias'),
    ('documentacao', 'Documentação'),
    ('usuarios', 'Usuários'),
    ('cadastros', 'Cadastros'),
)


def preserve_existing_companies(apps, schema_editor):
    using = schema_editor.connection.alias
    Module = apps.get_model('estoque', 'Modulo')
    Company = apps.get_model('estoque', 'Empresa')
    CompanyModule = apps.get_model('estoque', 'ModuloEmpresa')

    first_order = Module.objects.using(using).count() + 1
    modules = []
    for offset, (code, name) in enumerate(NEW_MODULES):
        module, _ = Module.objects.using(using).update_or_create(
            codigo=code,
            defaults={
                'nome': name,
                'ordem': first_order + offset,
                'ativo': True,
            },
        )
        modules.append(module)

    CompanyModule.objects.using(using).bulk_create(
        [
            CompanyModule(
                empresa_id=company_id,
                modulo_id=module.pk,
                habilitado=True,
            )
            for company_id in Company.objects.using(using).values_list('pk', flat=True)
            for module in modules
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0056_categorias_checklist_configuraveis'),
    ]

    operations = [
        migrations.AlterField(
            model_name='modulo',
            name='codigo',
            field=models.SlugField(
                choices=[
                    ('estoque', 'Estoque'),
                    ('equipamentos', 'Equipamentos'),
                    ('sick', 'SICK'),
                    ('transferencias', 'Transferências'),
                    ('emprestimos', 'Empréstimos'),
                    ('insumos', 'Insumos'),
                    ('checklist', 'Checklist'),
                    ('chamados', 'Chamados'),
                    ('ordens_servico', 'Ordens de serviço'),
                    ('catalogo', 'Catálogo'),
                    ('tory', 'Tory'),
                    ('auditorias', 'Auditorias'),
                    ('documentacao', 'Documentação'),
                    ('usuarios', 'Usuários'),
                    ('cadastros', 'Cadastros'),
                ],
                max_length=40,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name='moduloempresa',
            name='habilitado',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.RunPython(
            preserve_existing_companies,
            migrations.RunPython.noop,
        ),
    ]
