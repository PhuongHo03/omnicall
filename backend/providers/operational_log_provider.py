import json
from typing import Any, Protocol

from redis import Redis, RedisError

from backend.configs.settings import Settings, get_settings


class OperationalLogProviderError(RuntimeError):
    pass


class OperationalLogProvider(Protocol):
    def append(self, event: dict[str, Any]) -> str:
        ...

    def tail(self, limit: int) -> list[dict[str, Any]]:
        ...

    def clear(self) -> int:
        ...


class RedisOperationalLogProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=2,
        )

    def append(self, event: dict[str, Any]) -> str:
        try:
            event_id = self.client.xadd(
                self.settings.operational_log_stream_key,
                {"event": json.dumps(event, ensure_ascii=False, separators=(",", ":"))},
                maxlen=self.settings.operational_log_max_length,
                approximate=True,
            )
            self.client.expire(
                self.settings.operational_log_stream_key,
                self.settings.operational_log_ttl_seconds,
            )
        except RedisError as exc:
            raise OperationalLogProviderError("Redis operational log write failed.") from exc
        return str(event_id)

    def tail(self, limit: int) -> list[dict[str, Any]]:
        try:
            entries = self.client.xrevrange(
                self.settings.operational_log_stream_key,
                count=max(1, limit),
            )
        except RedisError as exc:
            raise OperationalLogProviderError("Redis operational log read failed.") from exc

        events: list[dict[str, Any]] = []
        for event_id, fields in entries:
            raw_event = fields.get("event")
            if not raw_event:
                continue
            try:
                event = json.loads(raw_event)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event["id"] = str(event_id)
            events.append(event)
        return events

    def clear(self) -> int:
        try:
            return int(self.client.delete(self.settings.operational_log_stream_key))
        except RedisError as exc:
            raise OperationalLogProviderError("Redis operational log clear failed.") from exc


def get_operational_log_provider() -> OperationalLogProvider:
    return RedisOperationalLogProvider(get_settings())
