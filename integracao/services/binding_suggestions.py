import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from estoque.models import Base
from insumos.models import Cliente


ALIASES = {
    "CAMPINAS": "CPN",
    "JUNDIAÍ": "JUNDIAI",
    "SÃO PAULO": "SP",
}


def normalize_name(value):
    text = unicodedata.normalize("NFKD", str(value or "").upper())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for original, replacement in ALIASES.items():
        original_normalized = normalize_name_without_aliases(original)
        text = re.sub(
            rf"\b{re.escape(original_normalized)}\b",
            normalize_name_without_aliases(replacement),
            text,
        )
    return re.sub(r"\s+", " ", text).strip()


def normalize_name_without_aliases(value):
    text = unicodedata.normalize("NFKD", str(value or "").upper())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def operational_comparison_name(value):
    text = normalize_name(value)
    text = re.sub(r"^OXXO\s+", "", text)
    text = re.sub(r"\s+X$", "", text)
    return text.strip()


def is_oxxo_base(base):
    name = normalize_name(getattr(base, "nome", base))
    return name.startswith("OXXO ") or name.endswith(" X")


def is_oxxo_client(client):
    return normalize_name(getattr(client, "sigla", "")) == "OXX"


@dataclass(frozen=True)
class BindingCandidate:
    instance: object
    score: int
    confidence: str
    reason: str


@dataclass(frozen=True)
class BindingSuggestion:
    candidates: tuple[BindingCandidate, ...]
    ambiguous: bool = False

    @property
    def best(self):
        return self.candidates[0] if self.candidates else None

    @property
    def can_bulk_confirm(self):
        return bool(
            self.best
            and self.best.confidence == "HIGH"
            and not self.ambiguous
        )


def _confidence(score, *, unique=True):
    if score >= 90 and unique:
        return "HIGH"
    if score >= 70:
        return "MEDIUM"
    return "LOW"


def _finalize(scored, limit):
    scored.sort(key=lambda item: (-item[1], str(item[0])))
    if not scored:
        return BindingSuggestion(())
    ambiguous = len(scored) > 1 and scored[0][1] - scored[1][1] < 5
    candidates = tuple(
        BindingCandidate(
            instance=instance,
            score=score,
            confidence=_confidence(score, unique=not (index == 0 and ambiguous)),
            reason=reason,
        )
        for index, (instance, score, reason) in enumerate(scored[:limit])
    )
    return BindingSuggestion(candidates=candidates, ambiguous=ambiguous)


def suggest_local_clients(planning_client, *, queryset=None, limit=5):
    queryset = queryset if queryset is not None else Cliente.objects.filter(ativo=True)
    external_names = {
        normalize_name(planning_client.trade_name),
        normalize_name(planning_client.corporate_name),
    } - {""}
    external_code = normalize_name(planning_client.code)
    external_text = " ".join(sorted(external_names | {external_code})).strip()
    external_is_oxxo = "OXXO" in external_text or "GRUPO NOS" in external_text
    store_codes = [
        normalize_name(code)
        for code in planning_client.stores.exclude(code="").values_list("code", flat=True)[:50]
    ]

    scored = []
    for client in queryset:
        local_name = normalize_name(client.nome)
        local_code = normalize_name(client.sigla)
        score = 0
        reasons = []
        if external_code and local_code == external_code:
            score = 100
            reasons.append("código externo igual à sigla local")
        if external_is_oxxo and local_code == "OXX":
            score = max(score, 98)
            reasons.append("alias confirmado OXXO/GRUPO NÓS → OXX")
        if local_name and local_name in external_names:
            score = max(score, 96)
            reasons.append("nome normalizado exato")
        if local_code and any(code.startswith(local_code) for code in store_codes):
            score = max(score, 88)
            reasons.append("sigla presente no início do código de loja")
        similarity = max(
            (SequenceMatcher(None, local_name, name).ratio() for name in external_names),
            default=0,
        )
        if similarity >= 0.65:
            similarity_score = round(similarity * 85)
            if similarity_score > score:
                score = similarity_score
                reasons = [f"similaridade de nome {similarity:.0%}"]
        if score >= 50:
            scored.append((client, score, "; ".join(dict.fromkeys(reasons))))
    return _finalize(scored, limit)


def suggest_operational_bases(
    planning_region,
    local_client,
    *,
    queryset=None,
    limit=5,
):
    queryset = queryset if queryset is not None else Base.objects.all()
    region_name = normalize_name(planning_region.name)
    region_core = operational_comparison_name(planning_region.name)
    wants_oxxo = is_oxxo_client(local_client)
    scored = []

    for base in queryset:
        base_name = normalize_name(base.nome)
        base_core = operational_comparison_name(base.nome)
        base_oxxo = is_oxxo_base(base)
        operation_matches = base_oxxo == wants_oxxo
        score = 0
        reasons = []

        if base_core == region_core or base_core == region_name:
            score = 100 if operation_matches else 55
            reasons.append("regional normalizada exata")
        elif region_core and (
            base_core.startswith(region_core + " ")
            or region_core.startswith(base_core + " ")
            or base_core.endswith(" " + region_core)
        ):
            score = 86 if operation_matches else 45
            reasons.append("regional normalizada com qualificador operacional")
        else:
            similarity = SequenceMatcher(None, base_core, region_core).ratio()
            if similarity >= 0.72:
                score = round(similarity * (82 if operation_matches else 50))
                reasons.append(f"similaridade regional {similarity:.0%}")

        if operation_matches and score:
            if wants_oxxo:
                reasons.append("base OXXO compatível com cliente OXX")
            else:
                reasons.append("base regular compatível com cliente não OXX")
        if score >= 40:
            scored.append((base, score, "; ".join(dict.fromkeys(reasons))))
    return _finalize(scored, limit)
