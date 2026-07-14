"""Canonical provenance items shared by extraction, retrieval, and chat."""

from collections.abc import Mapping


EVIDENCE_KINDS = frozenset({"transcript", "structured", "derived", "source"})


def build_evidence_item(
    *,
    evidence_id: str,
    kind: str,
    quote: str | None = None,
    segment_ids: list[str] | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    source_ref: str | None = None,
    json_pointer: str | None = None,
    derived_from: list[str] | None = None,
) -> dict:
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"Unsupported evidence kind: {kind}")
    return {
        "id": evidence_id,
        "kind": kind,
        "quote": quote,
        "segmentIds": _unique(segment_ids),
        "startMs": start_ms,
        "endMs": end_ms,
        "sourceRef": source_ref,
        "jsonPointer": json_pointer,
        "derivedFrom": _unique(derived_from),
    }


def evidence_items(result_json: Mapping[str, object]) -> list[dict]:
    evidence = result_json.get("evidence")
    if not isinstance(evidence, Mapping):
        return []
    items = evidence.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)]
    # JSON v2 has one authoritative evidence collection. Do not silently
    # reinterpret the removed v1 `evidence.citations` shape.
    return []


def evidence_by_id(result_json: Mapping[str, object]) -> dict[str, dict]:
    return {item["id"]: item for item in evidence_items(result_json)}


def _unique(values: list[str] | None) -> list[str]:
    return list(dict.fromkeys(value for value in (values or []) if isinstance(value, str) and value))
