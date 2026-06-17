import json
from typing import Any

from redis import Redis, RedisError

from backend.configs.settings import Settings, get_settings


class CacheProviderError(RuntimeError):
    pass


class JsonCacheProvider:
    def get_json(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        raise NotImplementedError


class RedisJsonCacheProvider(JsonCacheProvider):
    def __init__(self, settings: Settings) -> None:
        self.client = Redis.from_url(settings.redis_url, decode_responses=True)

    def get_json(self, key: str) -> dict[str, Any] | None:
        try:
            raw_value = self.client.get(key)
        except RedisError as exc:
            raise CacheProviderError("Redis cache read failed.") from exc
        if raw_value is None:
            return None
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise CacheProviderError("Redis cache value was not valid JSON.") from exc
        return value if isinstance(value, dict) else None

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        try:
            self.client.set(key, json.dumps(value), ex=ttl_seconds)
        except RedisError as exc:
            raise CacheProviderError("Redis cache write failed.") from exc


def get_json_cache_provider() -> JsonCacheProvider:
    return RedisJsonCacheProvider(get_settings())
