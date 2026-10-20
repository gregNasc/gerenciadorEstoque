import re
import unicodedata

from django.db import migrations


def _normalizar(valor):
    texto = unicodedata.normalize('NFKD', valor or '')
    texto = ''.join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return ' '.join(texto.upper().split())


def padronizar_botas(apps, schema_editor):
    Insumo = apps.get_model('insumos', 'Insumo')
    for insumo in Insumo.objects.select_related('categoria').iterator():
        descricao = _normalizar(insumo.descricao)
        categoria = _normalizar(insumo.categoria.nome)
        nome_com_intervalo = re.search(r'\d+\s*(?:/|A|ATE|-)\s*\d+', descricao)
        if categoria == 'EPI' and (
            descricao == 'BOTAS'
            or (descricao.startswith('BOTA') and nome_com_intervalo)
        ):
            Insumo.objects.filter(pk=insumo.pk).update(descricao='Botas')


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0045_normalizar_botas_e_operacionais'),
    ]

    operations = [
        migrations.RunPython(padronizar_botas, migrations.RunPython.noop),
    ]
