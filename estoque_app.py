import streamlit as st
import pandas as pd
from database import (
    criar_tabela,
    cadastrar_produto, listar_produtos,
    movimentar_estoque, transferir_equipamento,
    registrar_sick, listar_sick, listar_historico_transferencias, conectar
)

# ---------- Inicialização ----------
criar_tabela()
st.set_page_config(page_title="📦 Sistema de Estoque", layout="wide")
st.title("📦 Sistema de Gerenciamento de Estoque")

MENU_REGIONAIS = [
    "SÃO PAULO 🇧🇷", "RIO DE JANEIRO 🇧🇷", "BAURU 🇧🇷",
    "FLORIANÓPOLIS 🇧🇷","PORTO ALEGRE 🇧🇷", "CURITIBA 🇧🇷",
    "MARINGÁ 🇧🇷", "JOINVILE 🇧🇷", "CAMPINAS 🇧🇷",
    "CHILE 🇨🇱", "PERU 🇵🇪"
]

menu = st.sidebar.selectbox(
    "Menu",
    ["Cadastrar Produto", "Movimentar Estoque", "Consultar Estoque por Regional", "Equipamentos em Sick", "Histórico de Transferências"]
)

# ---------- CADASTRAR PRODUTO ----------
if menu == "Cadastrar Produto":
    st.subheader("➕ Cadastrar novo produto")
    descricao = st.text_input("Descrição do equipamento").strip().upper()
    codigo = st.text_input("Nº do Patrimônio")
    numero_serie = st.text_input("Nº de Série")
    quantidade = st.number_input("Quantidade inicial", min_value=0, step=1)
    regional = st.selectbox("Regional", MENU_REGIONAIS)

    if st.button("Salvar"):
        if descricao and codigo:
            produtos_existentes = listar_produtos()
            if any(p[2] == codigo for p in produtos_existentes):
                st.error(f"O código {codigo} já está cadastrado. Patrimônio deve ser único.")
            else:
                try:
                    cadastrar_produto(descricao, codigo, quantidade, regional)
                    st.success(f"Produto '{descricao}' cadastrado com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")
        else:
            st.warning("Preencha todos os campos!")

# ---------- MOVIMENTAR ESTOQUE ----------
elif menu == "Movimentar Estoque":
    st.subheader("🔄 Transferência de Equipamento / SICK")
    codigo = st.text_input("Nº do Patrimônio")
    qtd_mov = st.number_input("Quantidade", min_value=1, step=1)
    tipo = st.radio("Tipo de movimentação", ["Sick", "Transferência"])

    if tipo == "Sick":
        regional = st.selectbox("Regional", MENU_REGIONAIS)
        sick_check = st.checkbox("Registrar como Sick?")
        motivo_sick = ""
        if sick_check:
            motivo_sick = st.text_input("Motivo do Sick").strip().upper()

    if tipo == "Transferência":
        regional_origem = st.selectbox("Regional de Origem", MENU_REGIONAIS)
        regional_destino = st.selectbox("Regional de Destino", MENU_REGIONAIS)

    if st.button("Confirmar movimentação"):
        if tipo == "Sick":
            produtos = [p for p in listar_produtos() if p[2] == codigo and p[4] == regional]
            if not produtos:
                st.error(f"Produto {codigo} não encontrado na regional {regional}.")
            else:
                descricao_prod = produtos[0][1]
                if sick_check and motivo_sick:
                    registrar_sick(codigo, descricao_prod, regional, motivo_sick)
                    # Remover produto do estoque
                    conn = conectar()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM produtos WHERE codigo = %s AND regional = %s", (codigo, regional))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    st.success(f"Produto '{descricao_prod}' registrado como Sick com motivo: {motivo_sick} e removido do estoque.")
                else:
                    movimentar_estoque(codigo, qtd_mov, "saida")
                    st.success(f"Saída de {qtd_mov} unidades do produto {codigo} realizada com sucesso!")
        elif tipo == "Transferência":
            if regional_origem == regional_destino:
                st.error("A transferência deve ser feita entre regionais diferentes.")
            else:
                msg = transferir_equipamento(codigo, qtd_mov, regional_origem, regional_destino)
                st.success(msg)

# ---------- CONSULTAR ESTOQUE POR REGIONAL ----------
elif menu == "Consultar Estoque por Regional":
    st.subheader("📊 Consulta de Estoque por Regional")
    produtos = listar_produtos()
    if produtos:
        df = pd.DataFrame(produtos, columns=["ID", "Descrição", "Nº do Patrimônio", "Quantidade", "Regional"])
        regionais = df["Regional"].unique().tolist()
        regional_selecionada = st.selectbox("Regional", ["Todas"] + regionais)
        if regional_selecionada != "Todas":
            df = df[df["Regional"] == regional_selecionada]
        st.dataframe(df, width='stretch')
    else:
        st.info("Nenhum produto cadastrado ainda.")

# ---------- EQUIPAMENTOS EM SICK ----------
elif menu == "Equipamentos em Sick":
    st.subheader("📋 Equipamentos em Sick")
    registros = listar_sick()
    if registros:
        df = pd.DataFrame(registros, columns=["Código", "Descrição", "Regional", "Motivo", "Data"])
        st.dataframe(df, width='stretch')
    else:
        st.info("Nenhum equipamento registrado como Sick.")

# ---------- HISTÓRICO DE TRANSFERÊNCIAS ----------
elif menu == "Histórico de Transferências":
    st.subheader("📋 Histórico de Transferências entre Regionais")
    historico = listar_historico_transferencias()
    if historico:
        df = pd.DataFrame(historico, columns=["Código", "Descrição", "Quantidade", "Regional Origem", "Regional Destino", "Data"])
        st.dataframe(df, width='stretch')
    else:
        st.info("Nenhuma transferência registrada ainda.")
