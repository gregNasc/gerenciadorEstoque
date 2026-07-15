from integracao.exceptions import InventoryPlanningResponseError
from integracao.mappers.common import (
    integer_or_none,
    nested_id,
    parse_external_datetime,
    payload_hash,
    require_external_id,
    sanitize_data,
)


def _metrics(payload):
    result = []
    for item in payload.get("metrics") or []:
        if not isinstance(item, dict) or not item.get("metric"):
            continue
        result.append({
            "metric": str(item["metric"]).strip().upper(),
            "value": item.get("value"),
        })
    return result


def _metric_value(metrics, metric_name):
    for item in metrics:
        if item["metric"] == metric_name:
            return integer_or_none(item.get("value"))
    return None


def _headcount_from_import(import_data):
    for key in ("pessoasPrevistas", "PESSOAS", "pessoas", "plannedHeadcount"):
        if key in import_data:
            value = integer_or_none(import_data.get(key))
            if value is not None:
                return value
    return None


def map_event(payload):
    if not isinstance(payload, dict):
        raise InventoryPlanningResponseError("Evento externo possui formato inválido.")
    clean_import_data, sensitive_filtered = sanitize_data(payload.get("importData") or {})
    metrics = _metrics(payload)
    planned_pieces = integer_or_none(payload.get("plannedPieces"))
    if planned_pieces is None:
        planned_pieces = _metric_value(metrics, "PLANNED_PIECES")
    planned_headcount = _metric_value(metrics, "PLANNED_HEADCOUNT")
    if planned_headcount is None:
        planned_headcount = _headcount_from_import(clean_import_data)
    meeting_point = payload.get("meetingPoint") or {}
    parent = payload.get("parentEvent") or {}
    parent_external_id = str(
        payload.get("parentEventId")
        or (parent.get("id") if isinstance(parent, dict) else "")
        or ""
    ).strip()

    return {
        "external_id": require_external_id(payload),
        "status": str(payload.get("status") or "").strip().upper(),
        "planned_at": parse_external_datetime(
            payload.get("plannedAt"),
            required=True,
            field_name="plannedAt",
        ),
        "planned_pieces": planned_pieces,
        "planned_headcount": planned_headcount,
        "notes": str(payload.get("notes") or "").strip(),
        "parent_external_id": parent_external_id,
        "store_external_id": nested_id(payload, "store"),
        "client_external_id": nested_id(payload.get("store") or {}, "client"),
        "region_external_id": (
            nested_id(payload.get("store") or {}, "regional", "regionalId")
            or nested_id(payload.get("store") or {}, "region")
        ),
        "inventory_type_external_id": nested_id(payload, "inventoryType"),
        "import_data": clean_import_data,
        "import_key": str(payload.get("importKey") or "").strip(),
        "import_revision": str(payload.get("importRevision") or "").strip(),
        "metrics": metrics,
        "meeting_point_external_id": str(meeting_point.get("id") or "").strip()
        if isinstance(meeting_point, dict)
        else "",
        "meeting_point_name": str(meeting_point.get("name") or "").strip()
        if isinstance(meeting_point, dict)
        else "",
        "sensitive_data_filtered": sensitive_filtered,
        "source_payload_hash": payload_hash(payload),
        "external_created_at": parse_external_datetime(payload.get("createdAt")),
        "external_updated_at": parse_external_datetime(payload.get("updatedAt")),
        "nested_store": payload.get("store") if isinstance(payload.get("store"), dict) else None,
        "nested_type": payload.get("inventoryType")
        if isinstance(payload.get("inventoryType"), dict)
        else None,
    }


def flatten_events(items):
    flattened = {}

    def add(payload, inherited_parent_id=""):
        if not isinstance(payload, dict):
            return
        data = dict(payload)
        if inherited_parent_id and not data.get("parentEventId"):
            data["parentEventId"] = inherited_parent_id
        external_id = require_external_id(data)
        previous = flattened.get(external_id)
        if previous is None or len(data) > len(previous):
            flattened[external_id] = data
        for child in data.get("children") or []:
            add(child, external_id)

    for item in items:
        add(item)
    return list(flattened.values())

