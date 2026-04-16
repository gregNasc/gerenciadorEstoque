# test_urls.py
import os
import sys
import django

# Configurar Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gerenciadorEstoque.ver1.settings')
django.setup()

from django.urls import reverse, resolve

print("=== TESTANDO URLs ===")

# Teste todas as URLs importantes
urls_para_testar = [
    ('estoque:index', []),
    ('estoque:sick', []),
    ('estoque:historico', []),
    ('estoque:historico_detalhes', [1]),
    ('estoque:exportar_historico_csv', []),
]

for nome_url, args in urls_para_testar:
    try:
        url = reverse(nome_url, args=args)
        print(f"✅ {nome_url} -> {url}")
    except Exception as e:
        print(f"❌ {nome_url} -> ERRO: {e}")