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
        language: str | None = None,
        file: dict[str, Any] | None = None,
        job: dict[str, Any] | None = None,
        chat: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        duration_ms: int | None = None,
        details: dict[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        normalized_level = level.strip().lower()
        normalized_flow = flow.strip().lower()
        if normalized_level not in _LEVELS or normalized_flow not in _FLOWS:
            return
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": normalized_level,
            "flow": normalized_flow,
            "stage": stage.strip(),
            "status": status.strip(),
            "message": message.strip(),
            "workspaceId": workspace_id,
            "meetingId": meeting_id,
            "meetingName": meeting_name,
            "language": language,
            "file": file or {},
            "job": job or {},
            "chat": chat or {},
            "provider": provider,
            "model": model,
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
    ) -> list[dict[str, Any]]:
        scan_limit = self.settings.operational_log_max_length
        events = self.provider.tail(scan_limit)
        normalized_flow = flow.strip().lower() if flow else None
        normalized_level = level.strip().lower() if level else None
        search_term = search.strip().lower() if search else None
        filtered = []
        for event in events:
            if normalized_flow and event.get("flow") != normalized_flow:
                continue
            if normalized_level and event.get("level") != normalized_level:
                continue
            if search_term and search_term not in json_search_text(event):
                continue
            filtered.append(event)
            if len(filtered) >= limit:
                break
        return filtered

    def clear(self) -> int:
        return self.provider.clear()


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
