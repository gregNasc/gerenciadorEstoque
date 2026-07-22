"""Monta o contrato de resposta da interface da Tory.

Este módulo não consulta o banco e não altera o escopo de autorização. Ele
somente converte a resposta já produzida pelos serviços operacionais em uma
estrutura de apresentação previsível para o frontend.
"""

import re
import unicodedata
from copy import deepcopy
from uuid import uuid4


RESPOSTA_TEXTO = "texto"
RESPOSTA_INDICADOR = "indicador"
RESPOSTA_LISTA = "lista"
RESPOSTA_TABELA = "tabela"
RESPOSTA_AGRUPAMENTO = "agrupamento"
RESPOSTA_ACAO = "acao"
RESPOSTA_ERRO = "erro"

TIPOS_PERMITIDOS = {
    RESPOSTA_TEXTO,
    RESPOSTA_INDICADOR,
    RESPOSTA_LISTA,
    RESPOSTA_TABELA,
    RESPOSTA_AGRUPAMENTO,
    RESPOSTA_ACAO,
    RESPOSTA_ERRO,
}

_ITEM_LISTA = re.compile(
    r"^\s*(?:[-•]\s*)?(?P<nome>[^:|]{1,120}):\s*(?P<valor>.+?)\s*$"
)


def construir_resposta(resultado):
    """Devolve um envelope novo sem remover as chaves legadas da Tory."""
    resultado = deepcopy(resultado or {})
    mensagem = str(resultado.get("mensagem") or resultado.get("resposta") or "").strip()
    componentes = _componentes_fornecidos(resultado.get("componentes"))
    if not componentes:
        componentes = _componentes_do_texto(mensagem)
    _adicionar_drill_down(componentes, resultado.get("acoes"))

    tipo = resultado.get("tipo")
    if tipo not in TIPOS_PERMITIDOS:
        tipo = _tipo_principal(componentes)

    metadados = deepcopy(resultado.get("metadados") or {})
    metadados.setdefault("total", _total_resultados(componentes))
    metadados.setdefault("pagina", 1)
    metadados.setdefault("total_paginas", 1)

    envelope = resultado
    envelope.update({
        "sucesso": True,
        "mensagem": mensagem,
        "resposta": mensagem,
        "resposta_id": str(resultado.get("resposta_id") or uuid4()),
        "tipo": tipo,
        "dados": deepcopy(resultado.get("dados") or {}),
        "componentes": componentes,
        "acoes": _acoes_validas(resultado.get("acoes")),
        "metadados": metadados,
    })
    return envelope


def construir_erro(mensagem, *, codigo="processamento", status=500):
    """Cria uma falha controlada, sem detalhes técnicos."""
    mensagem = str(mensagem).strip()
    return {
        "sucesso": False,
        "mensagem": mensagem,
        "resposta": mensagem,
        "resposta_id": str(uuid4()),
        "tipo": RESPOSTA_ERRO,
        "dados": {},
        "componentes": [{"tipo": RESPOSTA_ERRO, "mensagem": mensagem}],
        "acoes": [],
        "metadados": {"total": 0, "pagina": 1, "total_paginas": 1},
        "erro": {"codigo": codigo, "status": status},
    }


def _componentes_fornecidos(componentes):
    if not isinstance(componentes, list):
        return []

    validos = []
    for componente in componentes:
        if not isinstance(componente, dict):
            continue
        tipo = componente.get("tipo")
        if tipo not in TIPOS_PERMITIDOS:
            continue
        validos.append(deepcopy(componente))
    return validos


def _componentes_do_texto(texto):
    if not texto:
        return []

    linhas = texto.splitlines()
    componentes = []
    buffer_texto = []
    indice = 0

    def descarregar_texto():
        if not buffer_texto:
            return
        bloco = "\n".join(buffer_texto).strip()
        buffer_texto.clear()
        if not bloco:
            return
        componente_lista = _como_lista(bloco)
        componentes.append(componente_lista or {"tipo": RESPOSTA_TEXTO, "texto": bloco})

    while indice < len(linhas):
        linha = linhas[indice]
        if _eh_cabecalho_tabela(linha):
            descarregar_texto()
            colunas = _celulas(linha)
            registros = []
            indice += 1
            while indice < len(linhas) and "|" in linhas[indice]:
                valores = _celulas(linhas[indice])
                if len(valores) == len(colunas):
                    registros.append(dict(zip(colunas, valores)))
                indice += 1
            componentes.append({
                "tipo": RESPOSTA_TABELA,
                "titulo": "Resultados",
                "colunas": [{"chave": coluna, "label": coluna} for coluna in colunas],
                "registros": registros,
            })
            continue

        buffer_texto.append(linha)
        indice += 1

    descarregar_texto()
    return componentes


def _como_lista(bloco):
    linhas = [linha.strip() for linha in bloco.splitlines() if linha.strip()]
    if len(linhas) < 2:
        return None

    titulo = ""
    itens = []
    for posicao, linha in enumerate(linhas):
        match = _ITEM_LISTA.match(linha)
        if not match:
            if posicao == 0 and linha.endswith(":"):
                titulo = linha[:-1]
                continue
            return None
        itens.append({"nome": match.group("nome").strip(), "valor": match.group("valor").strip()})

    if len(itens) < 2:
        return None
    return {"tipo": RESPOSTA_LISTA, "titulo": titulo, "itens": itens}


def _eh_cabecalho_tabela(linha):
    return "|" in linha and linha == linha.upper() and len(_celulas(linha)) > 1


def _celulas(linha):
    return [celula.strip() for celula in linha.strip().strip("|").split("|")]


def _tipo_principal(componentes):
    tipos = {item.get("tipo") for item in componentes}
    if RESPOSTA_ERRO in tipos:
        return RESPOSTA_ERRO
    if len(tipos) > 1:
        return RESPOSTA_AGRUPAMENTO
    return next(iter(tipos), RESPOSTA_TEXTO)


def _total_resultados(componentes):
    totais = [
        len(item.get("registros") or [])
        for item in componentes
        if item.get("tipo") == RESPOSTA_TABELA
    ]
    return max(totais, default=0)


def _acoes_validas(acoes):
    """Aceita somente ações declaradas pelo backend em formato conhecido."""
    if not isinstance(acoes, list):
        return []

    validas = []
    for acao in acoes:
        if not isinstance(acao, dict):
            continue
        label = str(acao.get("label") or acao.get("pergunta") or "").strip()
        if not label:
            continue
        normalizada = deepcopy(acao)
        normalizada["label"] = label
        validas.append(normalizada)
    return validas


def _adicionar_drill_down(componentes, acoes_backend):
    """Anexa somente consultas controladas a valores já autorizados da tabela.

    O frontend recebe a pergunta pronta e nunca deduz um comando a partir da
    célula. A consulta seguinte ainda passa novamente pelo serviço e por todo o
    escopo de permissões do usuário.
    """
    acoes_por_label = {
        str(acao.get("label") or "").strip().casefold(): deepcopy(acao)
        for acao in (acoes_backend or [])
        if isinstance(acao, dict) and acao.get("pergunta")
    }

    for componente in componentes:
        if componente.get("tipo") != RESPOSTA_TABELA:
            continue
        for registro in componente.get("registros") or []:
            if not isinstance(registro, dict):
                continue
            cliente = _valor_coluna(registro, "CLIENTE")
            acoes_celulas = {}
            for coluna, valor in list(registro.items()):
                if str(coluna).startswith("_"):
                    continue
                valor = str(valor or "").strip()
                if not valor or valor == "-":
                    continue
                coluna_normalizada = _normalizar_coluna(coluna)
                acao = None
                if coluna_normalizada in {"BASE", "REGIONAL"}:
                    acao = acoes_por_label.get(valor.casefold()) or {
                        "codigo": "drilldown_base",
                        "tipo": "consulta",
                        "label": valor,
                        "pergunta": f"Na base {valor}",
                    }
                elif coluna_normalizada == "PATRIMONIO":
                    acao = {
                        "codigo": "drilldown_equipamento",
                        "tipo": "consulta",
                        "label": valor,
                        "pergunta": f"Detalhe o equipamento de patrimônio {valor}",
                    }
                elif coluna_normalizada in {"SERIE", "NUMERO DE SERIE"}:
                    acao = {
                        "codigo": "drilldown_equipamento",
                        "tipo": "consulta",
                        "label": valor,
                        "pergunta": f"Detalhe o equipamento de série {valor}",
                    }
                elif coluna_normalizada == "CODIGO":
                    acao = {
                        "codigo": "drilldown_equipamento",
                        "tipo": "consulta",
                        "label": valor,
                        "pergunta": f"Detalhe o equipamento de código {valor}",
                    }
                elif coluna_normalizada == "LOJA" and cliente:
                    acao = {
                        "codigo": "drilldown_inventario",
                        "tipo": "consulta",
                        "label": valor,
                        "pergunta": f"Fale sobre o inventário {cliente} loja {valor}",
                    }
                elif coluna_normalizada in {"INVENTARIO", "CLIENTE/LOJA"}:
                    acao = {
                        "codigo": "drilldown_inventario",
                        "tipo": "consulta",
                        "label": valor,
                        "pergunta": f"Fale sobre o inventário {valor}",
                    }
                if acao:
                    acoes_celulas[coluna] = acao
            if acoes_celulas:
                registro["_acoes_celulas"] = acoes_celulas


def _normalizar_coluna(valor):
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(caractere)
    )
    return sem_acentos.strip().upper()


def _valor_coluna(registro, nome):
    for coluna, valor in registro.items():
        if _normalizar_coluna(coluna) == nome:
            return str(valor or "").strip()
    return ""
