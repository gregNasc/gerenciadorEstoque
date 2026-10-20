import re
import unicodedata

from django.db import migrations


def _normalizar(valor):
    texto = unicodedata.normalize('NFKD', valor or '')
    texto = ''.join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return ' '.join(texto.upper().split())


def normalizar_catalogo(apps, schema_editor):
    Insumo = apps.get_model('insumos', 'Insumo')
    alterados = []
    for insumo in Insumo.objects.select_related('categoria').iterator():
        descricao = _normalizar(insumo.descricao)
        categoria = _normalizar(insumo.categoria.nome)
        campos = []

        if descricao.startswith('BOTA') and re.search(r'\d+\s*(?:/|A|ATE|-)\s*\d+', descricao):
            insumo.descricao = 'Botas'
            campos.append('descricao')

        if categoria == 'OPERACIONAL' and (
            'ESCADA' in descricao or 'BALANCA' in descricao
        ):
            if insumo.natureza != 'REUTILIZAVEL':
                insumo.natureza = 'REUTILIZAVEL'
                campos.append('natureza')
            if insumo.forma_controle != 'INDIVIDUALIZADO':
                insumo.forma_controle = 'INDIVIDUALIZADO'
                campos.append('forma_controle')

        if campos:
            insumo.save(update_fields=campos)


class Migration(migrations.Migration):

    dependencies = [
        ('insumos', '0044_ativos_individualizados'),
    ]

    operations = [
        migrations.RunPython(normalizar_catalogo, migrations.RunPython.noop),
    ]
