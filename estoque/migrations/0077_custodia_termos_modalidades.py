from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0076_restringir_assuntos_jose_barboza'),
    ]

    operations = [
        migrations.AddField(model_name='custodia', name='modalidade_custodiante', field=models.CharField(choices=[('COLABORADOR', 'Colaborador'), ('PRESTADOR', 'Prestador de serviços')], default='COLABORADOR', max_length=20)),
        migrations.AddField(model_name='custodia', name='razao_social_responsavel', field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='custodia', name='cnpj_responsavel', field=models.CharField(blank=True, default='', max_length=20)),
        migrations.AddField(model_name='custodia', name='custodiante_cpf', field=models.CharField(blank=True, default='', max_length=20, verbose_name='CPF do custodiante')),
        migrations.AddField(model_name='custodia', name='custodiante_identificacao', field=models.CharField(blank=True, default='', max_length=100, verbose_name='Identificação do custodiante')),
        migrations.AddField(model_name='custodia', name='custodiante_funcao_atividade', field=models.CharField(blank=True, default='', max_length=150, verbose_name='Função / atividade')),
        migrations.AddField(model_name='custodia', name='custodiante_email', field=models.EmailField(blank=True, default='', max_length=254, verbose_name='E-mail do custodiante')),
        migrations.AddField(model_name='custodia', name='empresa_contratada', field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='custodia', name='cnpj_contratada', field=models.CharField(blank=True, default='', max_length=20)),
        migrations.AddField(model_name='custodia', name='responsavel_entrega_nome', field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='custodia', name='testemunha_1_nome', field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='custodia', name='testemunha_1_cpf', field=models.CharField(blank=True, default='', max_length=20)),
        migrations.AddField(model_name='custodia', name='testemunha_1_email', field=models.EmailField(blank=True, default='', max_length=254)),
        migrations.AddField(model_name='custodia', name='testemunha_2_nome', field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='custodia', name='testemunha_2_cpf', field=models.CharField(blank=True, default='', max_length=20)),
        migrations.AddField(model_name='custodia', name='testemunha_2_email', field=models.EmailField(blank=True, default='', max_length=254)),
        migrations.AddField(model_name='itemcustodia', name='acessorios_entregues', field=models.TextField(blank=True, default='', verbose_name='Acessórios / dados complementares na entrega')),
        migrations.AddField(model_name='devolucaocustodia', name='resultado_conferencia', field=models.CharField(choices=[('COMPLETA', 'Completa e sem divergências'), ('RESSALVAS', 'Completa com ressalvas'), ('PARCIAL', 'Parcial')], default='COMPLETA', max_length=20)),
        migrations.AddField(model_name='devolucaocustodia', name='pendencias', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='devolucaocustodia', name='responsavel_recebimento_email', field=models.EmailField(blank=True, default='', max_length=254)),
        migrations.AddField(model_name='devolucaocustodia', name='testemunha_1_nome', field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='devolucaocustodia', name='testemunha_1_cpf', field=models.CharField(blank=True, default='', max_length=20)),
        migrations.AddField(model_name='devolucaocustodia', name='testemunha_1_email', field=models.EmailField(blank=True, default='', max_length=254)),
        migrations.AddField(model_name='devolucaocustodia', name='testemunha_2_nome', field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='devolucaocustodia', name='testemunha_2_cpf', field=models.CharField(blank=True, default='', max_length=20)),
        migrations.AddField(model_name='devolucaocustodia', name='testemunha_2_email', field=models.EmailField(blank=True, default='', max_length=254)),
        migrations.AddField(model_name='itemdevolucaocustodia', name='acessorios_devolvidos', field=models.TextField(blank=True, default='')),
    ]
