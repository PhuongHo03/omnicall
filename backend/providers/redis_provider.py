import logging

from redis import Redis, ConnectionPool

from backend.configs.settings import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_client: Redis | None = None


def get_redis_client() -> Redis:
    global _pool, _client
    if _client is not None:
        return _client
    settings = get_settings()
    _pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True, max_connections=20)
    _client = Redis(connection_pool=_pool)
    return _client
