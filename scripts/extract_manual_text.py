"""Extrai texto dos PDFs locais para a busca contextual da Tory."""

import json
import sys
from pathlib import Path

from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = PROJECT_ROOT / 'estoque' / 'data' / 'manuais.json'
STATIC_ROOT = PROJECT_ROOT / 'estoque' / 'static'


def main():
    catalogo = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))['manuais']
    extraidos = 0
    for manual in catalogo:
        origem_relativa = manual.get('arquivo')
        destino_relativo = manual.get('texto')
        if not origem_relativa or not destino_relativo:
            continue
        origem = STATIC_ROOT / origem_relativa
        destino = STATIC_ROOT / destino_relativo
        if not origem.is_file():
            print(f'IGNORADO|{origem_relativa}|arquivo ausente')
            continue
        leitor = PdfReader(str(origem))
        paginas = []
        for numero, pagina in enumerate(leitor.pages, start=1):
            texto = (pagina.extract_text() or '').strip()
            if texto:
                paginas.append(f'Página {numero}\n\n{texto}')
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text('\n\n'.join(paginas), encoding='utf-8')
        extraidos += 1
        print(f'OK|{destino_relativo}|{len(paginas)} páginas')
    return 0 if extraidos else 1


if __name__ == '__main__':
    sys.exit(main())
