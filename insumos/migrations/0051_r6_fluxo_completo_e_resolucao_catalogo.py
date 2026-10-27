import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('insumos', '0050_r6_solicitacoes_unificadas_fundacao'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='solicitacaoinsumo',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDENTE', 'Aguardando Compras'),
                    ('RECEBIDA_COMPRAS', 'Recebida por Compras'),
                    ('EM_ANALISE', 'Em análise'),
                    ('APROVADA', 'Aprovada'),
                    ('REPROVADA', 'Reprovada'),
                    ('EM_COMPRA', 'Em compra (legado)'),
                    ('PEDIDO_REALIZADO', 'Pedido realizado'),
                    ('RECEBIDA', 'Recebida'),
                    ('FINALIZADA', 'Atendida'),
                ],
                default='PENDENTE',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='itemsolicitacaoinsumo',
            name='resolvido_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='itemsolicitacaoinsumo',
            name='resolvido_insumo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='novos_itens_solicitacao_resolvidos',
                to='insumos.insumo',
            ),
        ),
        migrations.AddField(
            model_name='itemsolicitacaoinsumo',
            name='resolvido_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='itens_solicitacao_resolvidos',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='itemsolicitacaoinsumo',
            name='resolvido_produto',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='novos_itens_solicitacao_resolvidos',
                to='estoque.produto',
            ),
        ),
        migrations.AddConstraint(
            model_name='itemsolicitacaoinsumo',
            constraint=models.CheckConstraint(
                condition=~models.Q(
                    resolvido_insumo__isnull=False,
                    resolvido_produto__isnull=False,
                ),
                name='item_solicitacao_uma_resolucao',
            ),
        ),
        migrations.AlterField(
            model_name='eventosolicitacaoinsumo',
            name='tipo',
            field=models.CharField(
                choices=[
                    ('CRIADA', 'Criada'),
                    ('RECEBIDA_COMPRAS', 'Recebida por Compras'),
                    ('EM_ANALISE', 'Em análise'),
                    ('APROVADA', 'Aprovada'),
                    ('REPROVADA', 'Reprovada'),
                    ('ENCAMINHADA_COMPRAS', 'Encaminhada para compra'),
                    ('PEDIDO_REALIZADO', 'Pedido realizado'),
                    ('RECEBIDA', 'Recebida'),
                    ('ATENDIDA', 'Atendida'),
                    ('ITEM_VINCULADO', 'Novo item vinculado ao catálogo'),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]
