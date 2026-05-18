from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AlocacaoSolicitacaoItem',
            fields=[
                ('id', models.BigAutoField(primary_key=True)),
                ('quantidade', models.PositiveIntegerField(default=0)),
                ('item', models.ForeignKey(
                    to='estoque.solicitacaoitem',
                    on_delete=models.CASCADE
                )),
                ('regional_origem', models.ForeignKey(
                    to='estoque.base',
                    on_delete=models.CASCADE
                )),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'estoque_alocacaosolicitacaoitem',
            },
        ),
    ]