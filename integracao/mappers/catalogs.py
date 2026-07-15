from integracao.mappers.common import (
    nested_id,
    parse_external_datetime,
    require_external_id,
)
from integracao.exceptions import InventoryPlanningResponseError


def map_region(payload):
    known = {"id", "name", "state", "isActive", "createdAt", "updatedAt"}
    return {
        "external_id": require_external_id(payload),
        "name": str(payload.get("name") or "").strip(),
        "state": str(payload.get("state") or "").strip().upper()[:2],
        "is_active": payload.get("isActive", True) is not False,
        "metadata": {key: value for key, value in payload.items() if key not in known},
        "external_created_at": parse_external_datetime(payload.get("createdAt")),
        "external_updated_at": parse_external_datetime(payload.get("updatedAt")),
    }


def map_client(payload):
    segment = payload.get("segment") or {}
    return {
        "external_id": require_external_id(payload),
        "corporate_name": str(payload.get("corporateName") or payload.get("name") or "").strip(),
        "trade_name": str(payload.get("tradeName") or "").strip(),
        "code": str(payload.get("code") or payload.get("acronym") or "").strip(),
        "segment_external_id": nested_id(payload, "segment"),
        "segment_name": str(segment.get("name") or "").strip() if isinstance(segment, dict) else "",
        "is_active": payload.get("isActive", True) is not False,
        "external_created_at": parse_external_datetime(payload.get("createdAt")),
        "external_updated_at": parse_external_datetime(payload.get("updatedAt")),
    }


def map_store(payload):
    return {
        "external_id": require_external_id(payload),
        "client_external_id": nested_id(payload, "client"),
        "region_external_id": nested_id(payload, "regional", "regionalId") or nested_id(payload, "region"),
        "code": str(payload.get("code") or "").strip(),
        "store_number": str(payload.get("storeNumber") or payload.get("number") or "").strip(),
        "name": str(payload.get("name") or "").strip(),
        "nickname": str(payload.get("nickname") or "").strip(),
        "corporate_document": str(payload.get("cnpj") or "").strip(),
        "address": str(payload.get("address") or "").strip(),
        "district": str(payload.get("district") or payload.get("addressDistrict") or "").strip(),
        "city": str(payload.get("city") or "").strip(),
        "state": str(payload.get("state") or "").strip().upper()[:2],
        "zip_code": str(payload.get("zipCode") or "").strip(),
        "is_active": payload.get("isActive", True) is not False,
        "external_created_at": parse_external_datetime(payload.get("createdAt")),
        "external_updated_at": parse_external_datetime(payload.get("updatedAt")),
    }


def map_inventory_type(payload):
    kind = str(payload.get("type") or "").strip().upper()
    if kind not in {"PAI", "FILHO"}:
        raise InventoryPlanningResponseError(
            "Tipo de inventário externo deve ser PAI ou FILHO."
        )
    return {
        "external_id": require_external_id(payload),
        "name": str(payload.get("name") or "").strip(),
        "code": str(payload.get("code") or "").strip(),
        "kind": kind,
        "description": str(payload.get("description") or "").strip(),
        "is_active": payload.get("isActive", True) is not False,
        "external_created_at": parse_external_datetime(payload.get("createdAt")),
        "external_updated_at": parse_external_datetime(payload.get("updatedAt")),
    }
