# test_urls.py
import os
import sys
import django

# Configurar Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'estoque_django.settings')

from django.urls import reverse

# Teste todas as URLs importantes
urls_para_testar = [
    ('estoque:index', []),
    ('estoque:sick', []),
    ('estoque:historico', []),
    ('estoque:historico_detalhes', [1]),
    ('estoque:exportar_historico_csv', []),
]

def main():
    django.setup()
    print("=== TESTANDO URLs ===")

    for nome_url, args in urls_para_testar:
        try:
            url = reverse(nome_url, args=args)
            print(f"OK {nome_url} -> {url}")
        except Exception as exc:
            print(f"ERRO {nome_url} -> {exc}")


if __name__ == '__main__':
    main()
