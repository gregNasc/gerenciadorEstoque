from decimal import Decimal

from django.db.models import Q, Sum
from django.shortcuts import render
from estoque.models import Base, Empresa
from insumos.models import MovimentacaoInsumo, SolicitacaoInsumo
from estoque.policies.compras import ComprasAccessPolicy
from insumos.views.saude_estoque import saude_estoque_required


ZERO = Decimal("0")
TRINTA_POR_CENTO = Decimal("0.30")
SETENTA_POR_CENTO = Decimal("0.70")
CEM = Decimal("100")

TIPOS_ENTRADA = [
    "ENTRADA",
    "DEVOLUCAO",
    "AJUSTE_ENTRADA",
]

TIPOS_SAIDA = [
    "SAIDA",
    "PERDA",
    "AJUSTE_SAIDA",
]


def _obter_referencia_estoque(estoque_minimo, estoque_maximo):
    """
    Define a referência usada para calcular a ocupação do estoque.

    Prioridade:
    1. Usa o estoque máximo quando estiver configurado.
    2. Se houver apenas estoque mínimo, infere o máximo considerando
       que o mínimo representa 30% da capacidade.
    3. Sem mínimo e sem máximo, o item fica sem parâmetro.
    """
    if estoque_maximo is not None and estoque_maximo > ZERO:
        return estoque_maximo, "maximo"

    if estoque_minimo is not None and estoque_minimo > ZERO:
        referencia_inferida = estoque_minimo / TRINTA_POR_CENTO
        return referencia_inferida, "inferido_minimo"

    return None, "sem_parametro"

def _calcular_percentual_estoque(saldo, referencia_estoque):
    """Calcula a ocupação percentual, limitada entre 0% e 100%."""
    if referencia_estoque is None or referencia_estoque <= ZERO:
        return None

    percentual = (saldo / referencia_estoque) * CEM

    return max(
        ZERO,
        min(percentual, CEM),
    )

def _classificar_saldo(saldo, estoque_minimo, estoque_maximo):
    """
    Classifica o saldo conforme a ocupação da referência de estoque.

    Regras:
    - Zerado: saldo menor ou igual a zero.
    - Crítico: acima de zero e até 30%.
    - Atenção: acima de 30% e abaixo de 70%.
    - Saudável: 70% ou mais.
    - Sem parâmetro: saldo positivo sem mínimo e sem máximo.
    """
    referencia, origem_referencia = _obter_referencia_estoque(
        estoque_minimo=estoque_minimo,
        estoque_maximo=estoque_maximo,
    )

    if saldo <= ZERO:
        return {
            "status": "zerado",
            "percentual": ZERO,
            "referencia": referencia,
            "origem_referencia": origem_referencia,
        }

    percentual = _calcular_percentual_estoque(
        saldo=saldo,
        referencia_estoque=referencia,
    )

    if percentual is None:
        return {
            "status": "sem_parametro",
            "percentual": None,
            "referencia": None,
            "origem_referencia": "sem_parametro",
        }

    if percentual <= Decimal("30"):
        status = "critico"
    elif percentual < Decimal("70"):
        status = "atencao"
    else:
        status = "saudavel"

    return {
        "status": status,
        "percentual": percentual,
        "referencia": referencia,
        "origem_referencia": origem_referencia,
    }

def _calcular_saude(registro):
    """
    Retorna a média da ocupação dos itens classificáveis.

    Itens positivos sem parâmetro são excluídos. Itens zerados entram
    com 0%, pois representam ruptura real do estoque monitorado.
    """
    quantidade = registro["itens_com_percentual"]

    if quantidade == 0:
        return None

    return round(
        registro["soma_percentuais"] / quantidade,
        1,
    )

def _definir_situacao_regional(registro):
    """
    Define a situação geral da regional pela média percentual
    de saúde dos itens monitorados.

    Regras:
    - Até 30%: crítica.
    - Acima de 30% e abaixo de 70%: atenção.
    - 70% ou mais: saudável.
    """
    if registro["total_itens"] == 0:
        return {
            "codigo": "sem_dados",
            "label": "Sem dados",
            "icone": "bi-dash-circle",
        }

    if registro["itens_com_percentual"] == 0:
        return {
            "codigo": "sem_parametro",
            "label": "Sem parâmetros",
            "icone": "bi-gear-fill",
        }

    saude = registro.get("saude")

    if saude is None:
        return {
            "codigo": "sem_parametro",
            "label": "Sem parâmetros",
            "icone": "bi-gear-fill",
        }

    if saude <= Decimal("30"):
        return {
            "codigo": "critico",
            "label": "Crítica",
            "icone": "bi-exclamation-octagon-fill",
        }

    if saude < Decimal("70"):
        return {
            "codigo": "atencao",
            "label": "Atenção",
            "icone": "bi-exclamation-triangle-fill",
        }

    return {
        "codigo": "saudavel",
        "label": "Saudável",
        "icone": "bi-check-circle-fill",
    }

def _prioridade_item_critico(item):
    """Ordena zerados primeiro e depois os menores percentuais."""
    prioridade_status = 0 if item["status"] == "zerado" else 1
    percentual = item["percentual"]

    if percentual is None:
        percentual = Decimal("999")

    return (
        prioridade_status,
        percentual,
        item["saldo"],
        item["insumo"].lower(),
    )

@saude_estoque_required
def dashboard_saude_insumos(request):
    if ComprasAccessPolicy.restrito(request.user):
        raise PermissionDenied('Sem permissão para visualizar a saúde do estoque.')
    empresa_id = (request.GET.get("empresa") or "").strip()
    base_id = (request.GET.get("base") or "").strip()

    if empresa_id and not empresa_id.isdigit():
        empresa_id = ""

    if base_id and not base_id.isdigit():
        base_id = ""

    empresas = list(
        Empresa.objects
        .filter(bases__isnull=False)
        .distinct()
        .order_by("nome")
    )

    bases_opcoes = list(
        Base.objects
        .select_related("empresa")
        .order_by("empresa__nome", "nome")
    )

    bases_consulta_qs = (
        Base.objects
        .select_related("empresa")
        .order_by("empresa__nome", "nome")
    )

    if empresa_id:
        bases_consulta_qs = bases_consulta_qs.filter(
            empresa_id=empresa_id
        )

    if base_id:
        bases_consulta_qs = bases_consulta_qs.filter(
            id=base_id
        )

    bases_consulta = list(bases_consulta_qs)
    bases_ids = [base.id for base in bases_consulta]

    regionais_por_id = {}

    for base in bases_consulta:
        regionais_por_id[base.id] = {
            "id": base.id,
            "nome": base.nome,
            "empresa_id": base.empresa_id,
            "empresa": base.empresa.nome,
            "total_itens": 0,
            "saudavel": 0,
            "atencao": 0,
            "critico": 0,
            "zerado": 0,
            "sem_parametro": 0,
            "valor_estoque": ZERO,
            "soma_percentuais": ZERO,
            "itens_com_percentual": 0,
            "saude": None,
            "saude_largura": 0,
            "tem_saude_calculada": False,
            "situacao": {},
            "tem_dados": False,
        }

    saldos_agregados = (
        MovimentacaoInsumo.objects
        .filter(
            base_id__in=bases_ids,
            insumo__ativo=True,
        )
        .values(
            "base_id",
            "insumo_id",
            "insumo__descricao",
            "insumo__categoria__nome",
            "insumo__unidade_medida",
            "insumo__estoque_minimo",
            "insumo__estoque_maximo",
            "insumo__valor_medio",
        )
        .annotate(
            entradas=Sum(
                "quantidade",
                filter=Q(tipo__in=TIPOS_ENTRADA),
            ),
            saidas=Sum(
                "quantidade",
                filter=Q(tipo__in=TIPOS_SAIDA),
            ),
        )
        .order_by(
            "base_id",
            "insumo__categoria__nome",
            "insumo__descricao",
        )
    )

    totais = {
        "saudavel": 0,
        "atencao": 0,
        "critico": 0,
        "zerado": 0,
        "sem_parametro": 0,
        "total_itens": 0,
        "valor_estoque": ZERO,
        "soma_percentuais": ZERO,
        "itens_com_percentual": 0,
    }

    itens_criticos = []

    for agregado in saldos_agregados:
        regional = regionais_por_id.get(agregado["base_id"])

        if regional is None:
            continue

        entradas = agregado["entradas"] or ZERO
        saidas = agregado["saidas"] or ZERO
        saldo = entradas - saidas

        estoque_minimo = (
            agregado["insumo__estoque_minimo"]
            or ZERO
        )

        estoque_maximo = (
            agregado["insumo__estoque_maximo"]
            or ZERO
        )

        valor_medio = (
            agregado["insumo__valor_medio"]
            or ZERO
        )

        classificacao = _classificar_saldo(
            saldo=saldo,
            estoque_minimo=estoque_minimo,
            estoque_maximo=estoque_maximo,
        )

        status = classificacao["status"]
        percentual_estoque = classificacao["percentual"]
        referencia_estoque = classificacao["referencia"]
        origem_referencia = classificacao["origem_referencia"]

        saldo_para_valor = max(saldo, ZERO)
        valor_item = saldo_para_valor * valor_medio

        regional["total_itens"] += 1
        regional[status] += 1
        regional["valor_estoque"] += valor_item

        totais["total_itens"] += 1
        totais[status] += 1
        totais["valor_estoque"] += valor_item

        if percentual_estoque is not None:
            regional["soma_percentuais"] += percentual_estoque
            regional["itens_com_percentual"] += 1

            totais["soma_percentuais"] += percentual_estoque
            totais["itens_com_percentual"] += 1

        if status in {"critico", "zerado"}:
            if referencia_estoque is not None:
                nivel_saudavel = (
                    referencia_estoque * SETENTA_POR_CENTO
                )
                deficit = max(
                    nivel_saudavel - saldo,
                    ZERO,
                )
            else:
                deficit = None

            itens_criticos.append({
                "base_id": regional["id"],
                "base": regional["nome"],
                "empresa_id": regional["empresa_id"],
                "empresa": regional["empresa"],
                "insumo_id": agregado["insumo_id"],
                "insumo": agregado["insumo__descricao"],
                "categoria": agregado["insumo__categoria__nome"],
                "unidade": agregado["insumo__unidade_medida"],
                "saldo": saldo,
                "minimo": estoque_minimo,
                "maximo": estoque_maximo,
                "referencia": referencia_estoque,
                "referencia_inferida": (
                    origem_referencia == "inferido_minimo"
                ),
                "tem_referencia": referencia_estoque is not None,
                "percentual": percentual_estoque,
                "tem_percentual": percentual_estoque is not None,
                "deficit": deficit,
                "tem_deficit": deficit is not None,
                "status": status,
                "status_label": (
                    "Zerado"
                    if status == "zerado"
                    else "Crítico"
                ),
            })

    regionais = list(regionais_por_id.values())

    for regional in regionais:
        regional["tem_dados"] = regional["total_itens"] > 0
        regional["saude"] = _calcular_saude(regional)
        regional["tem_saude_calculada"] = regional["saude"] is not None
        regional["saude_largura"] = (
            int(round(float(regional["saude"])))
            if regional["saude"] is not None
            else 0
        )
        regional["situacao"] = _definir_situacao_regional(
            regional
        )

    itens_criticos.sort(key=_prioridade_item_critico)
    itens_criticos = itens_criticos[:15]

    saude_geral = _calcular_saude(totais)

    bases_monitoradas = sum(
        1
        for regional in regionais
        if regional["tem_dados"]
    )

    bases_sem_dados = len(regionais) - bases_monitoradas

    solicitacoes_pendentes = (
        SolicitacaoInsumo.objects
        .filter(
            base_id__in=bases_ids,
            status="PENDENTE",
        )
        .count()
    )

    resumo = {
        "total_bases": len(regionais),
        "bases_monitoradas": bases_monitoradas,
        "bases_sem_dados": bases_sem_dados,
        "total_itens": totais["total_itens"],
        "saudaveis": totais["saudavel"],
        "atencao": totais["atencao"],
        "criticos": totais["critico"],
        "zerados": totais["zerado"],
        "sem_parametro": totais["sem_parametro"],
        "valor_estoque": totais["valor_estoque"],
        "saude_geral": saude_geral,
        "tem_dados": totais["total_itens"] > 0,
        "tem_saude_calculada": saude_geral is not None,
        "solicitacoes_pendentes": solicitacoes_pendentes,
    }

    grafico_saude_regionais = {
        "labels": [
            f'{regional["nome"]} · {regional["empresa"]}'
            for regional in regionais
        ],
        "saudavel": [
            regional["saudavel"]
            for regional in regionais
        ],
        "atencao": [
            regional["atencao"]
            for regional in regionais
        ],
        "critico": [
            regional["critico"]
            for regional in regionais
        ],
        "zerado": [
            regional["zerado"]
            for regional in regionais
        ],
        "sem_parametro": [
            regional["sem_parametro"]
            for regional in regionais
        ],
    }

    grafico_distribuicao = {
        "labels": [
            "Saudáveis",
            "Atenção",
            "Críticos",
            "Zerados",
            "Sem parâmetro",
        ],
        "valores": [
            totais["saudavel"],
            totais["atencao"],
            totais["critico"],
            totais["zerado"],
            totais["sem_parametro"],
        ],
    }

    return render(
        request,
        "insumos/dashboard/saude/dashboard_saude.html",
        {
            "empresas": empresas,
            "bases": bases_opcoes,
            "regionais": regionais,
            "resumo": resumo,
            "itens_criticos": itens_criticos,
            "grafico_saude_regionais": grafico_saude_regionais,
            "grafico_distribuicao": grafico_distribuicao,
            "filtro_empresa_id": empresa_id,
            "filtro_base_id": base_id,
        },
    )
