import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from integracao.constants import SENSITIVE_FIELD_TOKENS
from integracao.exceptions import InventoryPlanningResponseError


NORMALIZED_SENSITIVE_FIELD_TOKENS = {
    normalized
    for token in SENSITIVE_FIELD_TOKENS
    if (normalized := re.sub(r"[^a-z0-9]", "", token.lower()))
}
EXACT_SENSITIVE_FIELD_TOKENS = {"rg", "pis"}


def normalized_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def sanitize_data(value):
    filtered = False
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            clean_key = normalized_key(key)
            if (
                clean_key in EXACT_SENSITIVE_FIELD_TOKENS
                or any(
                    token in clean_key
                    for token in NORMALIZED_SENSITIVE_FIELD_TOKENS - EXACT_SENSITIVE_FIELD_TOKENS
                )
            ):
                filtered = True
                continue
            clean_item, item_filtered = sanitize_data(item)
            result[str(key)] = clean_item
            filtered = filtered or item_filtered
        return result, filtered
    if isinstance(value, list):
        result = []
        for item in value:
            clean_item, item_filtered = sanitize_data(item)
            result.append(clean_item)
            filtered = filtered or item_filtered
        return result, filtered
    return value, False


def parse_external_datetime(value, *, required=False, field_name="datetime"):
    if not value:
        if required:
            raise InventoryPlanningResponseError(f"Campo obrigatório ausente: {field_name}.")
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise InventoryPlanningResponseError(f"Data inválida no campo {field_name}.")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_default_timezone())
    return parsed


def integer_or_none(value):
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    if number < 0:
        return None
    return int(number)


def require_external_id(payload):
    external_id = str((payload or {}).get("id") or "").strip()
    if not external_id:
        raise InventoryPlanningResponseError("Registro externo sem id.")
    return external_id


def nested_id(payload, key, fallback_key=None):
    nested = payload.get(key) or {}
    if isinstance(nested, dict) and nested.get("id"):
        return str(nested["id"])
    value = payload.get(fallback_key or f"{key}Id")
    return str(value) if value else ""


def payload_hash(payload):
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
