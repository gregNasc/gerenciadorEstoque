import psycopg2
import os
import django

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gerenciadorEstoque.settings")
django.setup()

from estoque.models import Produto, Descricao, HistoricoTransferencia, Sick

# Conectar no PostgreSQL antigo (Streamlit)
conn = psycopg2.connect(
    dbname="estoque",
    user="postgres",
    password="admininventory",
    host="localhost",
    port=5432
)
cursor = conn.cursor()

# ---------- Migrar descricoes ----------
cursor.execute("SELECT descricao FROM descricoes")
for row in cursor.fetchall():
    Descricao.objects.get_or_create(descricao=row[0])

# ---------- Migrar produtos ----------
cursor.execute("SELECT descricao, codigo, quantidade, regional FROM produtos")
for row in cursor.fetchall():
    Produto.objects.get_or_create(
        descricao=row[0],
        codigo=row[1],
        quantidade=row[2],
        regional=row[3]
    )

# ---------- Migrar histórico de transferências ----------
cursor.execute("SELECT codigo, descricao, quantidade, regional_origem, regional_destino, data_movimentacao FROM historico_transferencias")
for row in cursor.fetchall():
    HistoricoTransferencia.objects.get_or_create(
        codigo=row[0],
        descricao=row[1],
        quantidade=row[2],
        regional_origem=row[3],
        regional_destino=row[4],
        data_movimentacao=row[5]
    )

# ---------- Migrar Sick ----------
cursor.execute("SELECT codigo, descricao, regional, motivo, data_ocorrencia FROM sick")
for row in cursor.fetchall():
    Sick.objects.get_or_create(
        codigo=row[0],
        descricao=row[1],
        regional=row[2],
        motivo=row[3],
        data_ocorrencia=row[4]
    )

cursor.close()
conn.close()

print("Migração concluída com sucesso!")
