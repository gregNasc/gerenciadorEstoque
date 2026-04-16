import psycopg2
import json
from datetime import datetime

# ---------- CONFIGURAÇÃO DO POSTGRESQL ----------
DB_PARAMS = {
    'dbname': 'estoque',
    'user': 'postgres',
    'password': 'admininventory',
    'host': 'localhost',
    'port': 5432
}

def conectar():
    return psycopg2.connect(**DB_PARAMS)

# ---------- TABELAS ----------
def criar_tabela():
    conn = conectar()
    cursor = conn.cursor()

    # Produtos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id SERIAL PRIMARY KEY,
        descricao TEXT NOT NULL,
        codigo TEXT NOT NULL UNIQUE,
        quantidade INTEGER NOT NULL,
        regional TEXT NOT NULL
    )
    """)

    # Descricoes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS descricoes (
        id SERIAL PRIMARY KEY,
        descricao TEXT NOT NULL UNIQUE
    )
    """)

    # Histórico de transferências
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historico_transferencias (
        id SERIAL PRIMARY KEY,
        codigo TEXT NOT NULL,
        descricao TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        regional_origem TEXT NOT NULL,
        regional_destino TEXT NOT NULL,
        data_movimentacao TIMESTAMP NOT NULL
    )
    """)

    # Sick
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sick (
        id SERIAL PRIMARY KEY,
        codigo TEXT NOT NULL,
        descricao TEXT NOT NULL,
        regional TEXT NOT NULL,
        motivo TEXT NOT NULL,
        data_ocorrencia TIMESTAMP NOT NULL
    )
    """)

    conn.commit()
    cursor.close()
    conn.close()

# ---------- DESCRIÇÕES ----------
def salvar_descricao(descricao: str):
    if not descricao:
        return
    descricao = descricao.strip().upper()
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO descricoes (descricao) VALUES (%s)
        ON CONFLICT (descricao) DO NOTHING
    """, (descricao,))
    conn.commit()
    cursor.close()
    conn.close()

def listar_descricoes():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT descricao FROM descricoes ORDER BY descricao ASC")
    rows = [r[0] for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return rows

# ---------- PRODUTOS ----------
def cadastrar_produto(descricao, codigo, quantidade, regional):
    descricao = descricao.strip().upper()
    salvar_descricao(descricao)
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO produtos (descricao, codigo, quantidade, regional)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (codigo) DO NOTHING
    """, (descricao, codigo, quantidade, regional))
    conn.commit()
    cursor.close()
    conn.close()

def listar_produtos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, descricao, codigo, quantidade, regional FROM produtos")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def movimentar_estoque(codigo, qtd, tipo="saida"):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT quantidade FROM produtos WHERE codigo = %s", (codigo,))
    result = cursor.fetchone()
    if result:
        quantidade_atual = result[0]
        if tipo == "entrada":
            nova_qtd = quantidade_atual + qtd
        else:
            nova_qtd = quantidade_atual - qtd if quantidade_atual >= qtd else quantidade_atual
        cursor.execute("UPDATE produtos SET quantidade = %s WHERE codigo = %s", (nova_qtd, codigo))
        conn.commit()
    cursor.close()
    conn.close()

def transferir_equipamento(codigo, qtd, regional_origem, regional_destino):
    if regional_origem == regional_destino:
        return "A transferência deve ser feita entre regionais diferentes."

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT descricao, quantidade FROM produtos WHERE codigo = %s AND regional = %s",
        (codigo, regional_origem)
    )
    origem = cursor.fetchone()

    if not origem:
        cursor.close()
        conn.close()
        return f"Produto {codigo} não encontrado na regional {regional_origem}."

    descricao, qtd_origem = origem

    if qtd_origem < qtd:
        cursor.close()
        conn.close()
        return f"Quantidade insuficiente. Estoque disponível: {qtd_origem}."

    # Atualizar estoque na origem
    nova_qtd_origem = qtd_origem - qtd
    if nova_qtd_origem > 0:
        cursor.execute(
            "UPDATE produtos SET quantidade = %s WHERE codigo = %s AND regional = %s",
            (nova_qtd_origem, codigo, regional_origem)
        )
    else:
        cursor.execute(
            "DELETE FROM produtos WHERE codigo = %s AND regional = %s",
            (codigo, regional_origem)
        )

    # Atualizar ou inserir na regional destino
    cursor.execute(
        "SELECT quantidade FROM produtos WHERE codigo = %s AND regional = %s",
        (codigo, regional_destino)
    )
    destino = cursor.fetchone()

    if destino:
        nova_qtd_destino = destino[0] + qtd
        cursor.execute(
            "UPDATE produtos SET quantidade = %s WHERE codigo = %s AND regional = %s",
            (nova_qtd_destino, codigo, regional_destino)
        )
    else:
        cursor.execute(
            "INSERT INTO produtos (descricao, codigo, quantidade, regional) VALUES (%s, %s, %s, %s)",
            (descricao, codigo, qtd, regional_destino)
        )

    # Registrar no histórico
    data_atual = datetime.now()
    cursor.execute("""
        INSERT INTO historico_transferencias (codigo, descricao, quantidade, regional_origem, regional_destino, data_movimentacao)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (codigo, descricao, qtd, regional_origem, regional_destino, data_atual))

    conn.commit()
    cursor.close()
    conn.close()
    return f"Transferência de {qtd} unidades do produto '{descricao}' realizada de {regional_origem} para {regional_destino}."

# ---------- SICK ----------
def registrar_sick(codigo, descricao, regional, motivo):
    conn = conectar()
    cursor = conn.cursor()
    data_atual = datetime.now()
    cursor.execute(
        "INSERT INTO sick (codigo, descricao, regional, motivo, data_ocorrencia) VALUES (%s, %s, %s, %s, %s)",
        (codigo, descricao, regional, motivo, data_atual)
    )
    conn.commit()
    cursor.close()
    conn.close()

def listar_sick():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT codigo, descricao, regional, motivo, data_ocorrencia FROM sick")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

# ---------- HISTÓRICO ----------
def listar_historico_transferencias():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT codigo, descricao, quantidade, regional_origem, regional_destino, data_movimentacao
        FROM historico_transferencias
        ORDER BY data_movimentacao DESC
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows
