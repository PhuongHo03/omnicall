import logging
from datetime import UTC, datetime
from typing import Any

from backend.configs.settings import Settings, get_settings
from backend.providers.operational_log_provider import (
    OperationalLogProvider,
    OperationalLogProviderError,
    get_operational_log_provider,
)

logger = logging.getLogger(__name__)

_LEVELS = {"info", "error"}
_FLOWS = {"processing", "rag"}
_MAX_STRING_LENGTH = 1000
_MAX_LIST_ITEMS = 30
_MAX_DICT_ITEMS = 50

_EXECUTOR_TYPES = {
    "llm", "embedding", "vector_store", "guardrail", "rule", "worker",
    "cache", "asr", "diarization", "audio_processing", "pipeline", "local",
}


class OperationalLogService:
    def __init__(
        self,
        provider: OperationalLogProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or get_operational_log_provider()

    def emit(
        self,
        *,
        level: str,
        flow: str,
        stage: str,
        status: str,
        message: str,
        workspace_id: str | None = None,
        meeting_id: str | None = None,
        meeting_name: str | None = None,
        file: dict[str, Any] | None = None,
        chat: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        executor_type: str | None = None,
        resource: str | None = None,
        operation: str | None = None,
        version: str | None = None,
        configured_provider: str | None = None,
        configured_model: str | None = None,
        effective_provider: str | None = None,
        effective_model: str | None = None,
        origin_provider: str | None = None,
        origin_model: str | None = None,
        fallback_used: bool | None = None,
        duration_ms: int | None = None,
        details: dict[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        normalized_level = level.strip().lower()
        normalized_flow = flow.strip().lower()
        if normalized_level not in _LEVELS or normalized_flow not in _FLOWS:
            return
        normalized_stage = stage.strip()
        normalized_executor = _executor_type(
            executor_type=executor_type,
            stage=normalized_stage,
            provider=provider,
        )
        # The legacy model slot used to contain collections, rules, and local
        # implementation versions. Normalize new events while retaining the
        # richer, correctly typed value in the provenance contract.
        if normalized_executor == "vector_store" and resource is None:
            resource, model = model, None
        elif normalized_executor == "rule" and resource is None:
            resource, model = model, None
        elif normalized_executor in {"audio_processing", "pipeline"} and version is None:
            version, model = model, None
        effective_provider = effective_provider or provider
        effective_model = effective_model or model
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": normalized_level,
            "flow": normalized_flow,
            "stage": normalized_stage,
            "status": status.strip(),
            "message": message.strip(),
            "workspaceId": workspace_id,
            "meetingId": meeting_id,
            "meetingName": meeting_name,
            "file": file or {},
            "chat": chat or {},
            "provider": provider,
            "model": model,
            "executorType": normalized_executor,
            "resource": resource,
            "operation": operation or normalized_stage,
            "version": version,
            "configuredProvider": configured_provider,
            "configuredModel": configured_model,
            "effectiveProvider": effective_provider,
            "effectiveModel": effective_model,
            "originProvider": origin_provider,
            "originModel": origin_model,
            "fallbackUsed": fallback_used,
            "durationMs": duration_ms,
            "details": details or {},
            "errorType": error_type,
            "errorMessage": error_message,
        }
        try:
            self.provider.append(_sanitize(event))
        except OperationalLogProviderError:
            logger.warning("Operational log event could not be written.", exc_info=True)


    def tail(
        self,
        *,
        limit: int,
        flow: str | None = None,
        level: str | None = None,
        search: str | None = None,
        meeting_id: str | None = None,
    ) -> list[dict[str, Any]]:
        scan_limit = self.settings.operational_log_max_length
        events = self.provider.tail(scan_limit)
        normalized_flow = flow.strip().lower() if flow else None
        normalized_level = level.strip().lower() if level else None
        search_term = search.strip().lower() if search else None
        normalized_meeting_id = meeting_id.strip() if meeting_id else None
        filtered = []
        for stored_event in events:
            event = _with_provenance_defaults(stored_event)
            if normalized_flow and event.get("flow") != normalized_flow:
                continue
            if normalized_level and event.get("level") != normalized_level:
                continue
            if normalized_meeting_id and event.get("meetingId") != normalized_meeting_id:
                continue
            if search_term and search_term not in json_search_text(event):
                continue
            filtered.append(event)
            if len(filtered) >= limit:
                break
        return filtered

    def tail_meetings(self) -> list[dict[str, Any]]:
        scan_limit = self.settings.operational_log_max_length
        events = self.provider.tail(scan_limit)
        meetings: dict[str, dict[str, Any]] = {}
        for event in events:
            mid = event.get("meetingId")
            if not mid:
                continue
            if mid not in meetings:
                meetings[mid] = {
                    "meetingId": mid,
                    "meetingName": event.get("meetingName"),
                    "processingCount": 0,
                    "ragCount": 0,
                    "latestTimestamp": event.get("timestamp"),
                    "latestLevel": event.get("level"),
                }
            entry = meetings[mid]
            if event.get("flow") == "processing":
                entry["processingCount"] += 1
            elif event.get("flow") == "rag":
                entry["ragCount"] += 1
            if event.get("timestamp", "") >= (entry["latestTimestamp"] or ""):
                entry["latestTimestamp"] = event.get("timestamp")
                entry["latestLevel"] = event.get("level")
                entry["meetingName"] = event.get("meetingName")
        result = sorted(meetings.values(), key=lambda m: m.get("latestTimestamp") or "", reverse=True)
        return result

    def clear(self) -> int:
        return self.provider.clear()

    def clear_by_meeting(self, meeting_id: str) -> int:
        scan_limit = self.settings.operational_log_max_length
        events = self.provider.tail(scan_limit)
        ids_to_delete = [
            event["id"]
            for event in events
            if event.get("meetingId") == meeting_id and "id" in event
        ]
        if not ids_to_delete:
            return 0
        return self.provider.delete_events(ids_to_delete)


def _executor_type(*, executor_type: str | None, stage: str, provider: str | None) -> str | None:
    explicit = (executor_type or "").strip().lower()
    if explicit in _EXECUTOR_TYPES:
        return explicit
    normalized_provider = (provider or "").strip().lower()
    if normalized_provider == "rule-based":
        return "rule"
    if stage in {"query_resolution", "agent", "answer", "analysis", "analysis_llm_primary"}:
        return "llm"
    if stage == "embedding":
        return "embedding"
    if stage == "vector_upsert":
        return "vector_store"
    if "guardrail" in stage:
        return "guardrail"
    if stage in {"worker_received", "queued", "worker_lock"}:
        return "worker"
    if stage in {"asr", "transcription"}:
        return "asr" if stage == "asr" or "router" not in normalized_provider else "pipeline"
    if stage == "diarization":
        return "diarization"
    if stage in {"audio_preprocessing", "vad"}:
        return "audio_processing"
    return "pipeline" if stage else None


def _with_provenance_defaults(stored_event: dict[str, Any]) -> dict[str, Any]:
    event = dict(stored_event)
    executor_type = _executor_type(
        executor_type=event.get("executorType"),
        stage=str(event.get("stage") or ""),
        provider=event.get("provider"),
    )
    event["executorType"] = executor_type
    if executor_type in {"vector_store", "rule"} and not event.get("resource"):
        event["resource"] = event.get("model")
        event["model"] = None
    elif executor_type in {"audio_processing", "pipeline"} and not event.get("version"):
        event["version"] = event.get("model")
        event["model"] = None
    event.setdefault("operation", event.get("stage"))
    event.setdefault("resource", None)
    event.setdefault("version", None)
    event.setdefault("configuredProvider", None)
    event.setdefault("configuredModel", None)
    event.setdefault("effectiveProvider", event.get("provider"))
    event.setdefault("effectiveModel", event.get("model"))
    event.setdefault("originProvider", None)
    event.setdefault("originModel", None)
    event.setdefault("fallbackUsed", None)
    return event


def get_operational_log_service() -> OperationalLogService:
    return OperationalLogService()


def json_search_text(event: dict[str, Any]) -> str:
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)
        elif value is not None:
            values.append(str(value))

    collect(event)
    return " ".join(values).lower()


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if isinstance(value, str):
        return value[:_MAX_STRING_LENGTH]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for index, (key, nested) in enumerate(value.items()):
            if index >= _MAX_DICT_ITEMS:
                sanitized["_truncated"] = True
                break
            if _is_sensitive_key(str(key)):
                sanitized[str(key)] = "[redacted]"
            else:
                sanitized[str(key)] = _sanitize(nested, depth=depth + 1)
        return sanitized
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        sanitized = [_sanitize(item, depth=depth + 1) for item in items[:_MAX_LIST_ITEMS]]
        if len(items) > _MAX_LIST_ITEMS:
            sanitized.append("[truncated]")
        return sanitized
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:_MAX_STRING_LENGTH]


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("_", "")
    return (
        normalized in {
            "apikey",
            "authorization",
            "password",
            "secret",
            "token",
            "accesstoken",
            "refreshtoken",
            "systemprompt",
            "userprompt",
            "prompt",
            "transcript",
            "rawtranscript",
        }
        or normalized.endswith("apikey")
        or normalized.endswith("password")
        or normalized.endswith("secret")
    )
