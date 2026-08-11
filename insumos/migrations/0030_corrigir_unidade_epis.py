import re
import unicodedata

from django.db import migrations


ORIGEM = 'MIGRACAO_UNIDADE_EPI_20260811'
PADRAO_EPI = re.compile(r'\b(mascara|touca|luva)s?\b')


def _normalizar(texto):
    return unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode().lower()


def corrigir_unidades(apps, schema_editor):
    Insumo = apps.get_model('insumos', 'Insumo')
    Historico = apps.get_model('insumos', 'HistoricoCadastroInsumo')

    for insumo in Insumo.objects.all().iterator():
        unidade_atual = (insumo.unidade_medida or '').strip()
        if unidade_atual.upper() != 'CX' or not PADRAO_EPI.search(_normalizar(insumo.descricao)):
            continue
        if Historico.objects.filter(insumo_id=insumo.pk, origem=ORIGEM).exists():
            continue

        Historico.objects.create(
            insumo_id=insumo.pk,
            campo='unidade_medida',
            valor_anterior=insumo.unidade_medida,
            valor_novo='UN',
            motivo='PADRONIZACAO DE MASCARA, TOUCA E LUVA PARA UNIDADE.',
            origem=ORIGEM,
        )
        Insumo.objects.filter(pk=insumo.pk).update(unidade_medida='UN')


def reverter_unidades(apps, schema_editor):
    Insumo = apps.get_model('insumos', 'Insumo')
    Historico = apps.get_model('insumos', 'HistoricoCadastroInsumo')

    historicos = Historico.objects.filter(origem=ORIGEM).order_by('-id')
    for historico in historicos.iterator():
        Insumo.objects.filter(pk=historico.insumo_id).update(
            unidade_medida=historico.valor_anterior
        )
    historicos.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0029_historicocadastroinsumo'),
    ]

    operations = [
        migrations.RunPython(corrigir_unidades, reverter_unidades),
    ]
