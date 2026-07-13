"""Pure text and record helpers used when building retrieval chunks."""

import re
import time
from collections.abc import Iterable


def citations_by_id(result_json: dict) -> dict[str, dict]:
    citations = result_json.get("evidence", {}).get("citations", [])
    if not isinstance(citations, list):
        return {}
    return {citation["id"]: citation for citation in citations if isinstance(citation, dict) and isinstance(citation.get("id"), str)}


def citation_ids(item: object) -> list[str]:
    if not isinstance(item, dict):
        return []
    value = item.get("citationIds")
    return [entry for entry in value if isinstance(entry, str)] if isinstance(value, list) else []


def record_id(item: dict, fallback: str) -> str:
    value = item.get("id")
    return value if isinstance(value, str) and value else fallback


def record_label(item: dict, index: int) -> str:
    for key in ("title", "displayName", "name", "task", "text", "type", "id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Record {index}"


def section_items(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    if isinstance(value, dict):
        return [value]
    return []


def metadata_text(value: object, *, heading: str | None = None) -> str:
    parts: list[str] = [heading] if heading else []
    parts.extend(flatten_metadata(value))
    return ". ".join(part for part in parts if part).strip()


def flatten_metadata(value: object, *, prefix: str | None = None, depth: int = 0) -> list[str]:
    if depth > 4 or value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        return [f"{labelize(prefix)}: {stripped}" if prefix else stripped]
    if isinstance(value, bool | int | float):
        return [f"{labelize(prefix)}: {value}" if prefix else str(value)]
    if isinstance(value, list):
        return flatten_list(value, prefix=prefix, depth=depth)
    if isinstance(value, dict):
        flattened: list[str] = []
        for key in ordered_keys(value):
            if key == "embedding":
                continue
            nested_prefix = key if prefix is None else f"{prefix} {key}"
            flattened.extend(flatten_metadata(value.get(key), prefix=nested_prefix, depth=depth + 1))
        return flattened
    return [f"{labelize(prefix)}: {value}" if prefix else str(value)]


def flatten_list(value: Iterable, *, prefix: str | None, depth: int) -> list[str]:
    flattened: list[str] = []
    scalar_values = [str(item).strip() for item in value if isinstance(item, str | bool | int | float) and str(item).strip()]
    if scalar_values:
        flattened.append(f"{labelize(prefix)}: {join_values(scalar_values)}" if prefix else join_values(scalar_values))
    for index, item in enumerate(value):
        if isinstance(item, dict):
            nested_prefix = f"{prefix} {index + 1}" if prefix else f"item {index + 1}"
            flattened.extend(flatten_metadata(item, prefix=nested_prefix, depth=depth + 1))
    return flattened


def ordered_keys(value: dict) -> list[str]:
    preferred = [
        "id", "type", "title", "displayName", "normalizedName", "label", "speakerLabel", "speakerLabels",
        "role", "organization", "subject", "predicate", "value", "unit", "task", "ownerParticipantId",
        "ownerName", "status", "priority", "dueAt", "occurredAt", "startMs", "endMs", "confidence",
        "description", "summary", "text", "quote", "citationIds", "segmentIds", "participantIds",
        "entityIds", "factIds", "eventIds", "topicIds",
    ]
    keys = [key for key in preferred if key in value]
    keys.extend(key for key in value.keys() if key not in keys)
    return keys


def labelize(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ").replace("-", " ")


def join_values(value: object) -> str:
    return ", ".join(str(item) for item in value if item is not None) if isinstance(value, list) else str(value)


def format_ms(value: object) -> str:
    if not isinstance(value, int | float) or value < 0:
        return "unknown time"
    total_seconds = int(value / 1000)
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def is_signal_text(text: str, *, min_tokens: int = 3) -> bool:
    return len(tokens(text)) >= min_tokens


def tokens(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE)


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
