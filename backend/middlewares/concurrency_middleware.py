import atexit
import logging

import redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.configs.settings import get_settings
from backend.providers.redis_provider import get_redis_client
from backend.utils.middleware_helpers import identify_account_for_concurrency, match_route_group

logger = logging.getLogger(__name__)

_ROUTE_GROUPS: list[tuple[str, str]] = [
    ("POST /api/auth/register", "auth"),
    ("POST /api/auth/", "auth"),
    ("GET /api/meetings", "meetings"),
    ("POST /api/meetings", "meetings"),
    ("PATCH /api/meetings", "meetings"),
    ("DELETE /api/meetings", "meetings"),
    ("GET /api/me", "meetings"),
    ("GET /api/admin/", "admin"),
    ("POST /api/admin/", "admin"),
    ("PATCH /api/admin/", "admin"),
    ("DELETE /api/admin/", "admin"),
]

def _concurrency_limit_for_group(group: str, settings) -> int:
    if group == "meetings":
        return settings.concurrency_limit_meetings
    if group == "admin":
        return settings.concurrency_limit_admin
    if group == "auth":
        return settings.concurrency_limit_auth
    return settings.concurrency_limit_per_account


_active_keys: set[str] = set()


def _cleanup_concurrency_counters() -> None:
    """Best-effort cleanup of concurrency counters on shutdown."""
    try:
        r = get_redis_client()
        for key in list(_active_keys):
            try:
                r.delete(key)
            except redis.RedisError:
                pass
        _active_keys.clear()
    except Exception:
        pass


atexit.register(_cleanup_concurrency_counters)


class ConcurrencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()

        group = match_route_group(request, _ROUTE_GROUPS)
        if group is None:
            return await call_next(request)

        account_hash = identify_account_for_concurrency(request)
        key = f"concurrency:{account_hash}:{group}"
        limit = _concurrency_limit_for_group(group, settings)

        r = get_redis_client()
        current = None

        try:
            current = r.incr(key)
            try:
                r.expire(key, 60)
            except redis.RedisError:
                logger.warning("Concurrency limit Redis expire failed, allowing request (fail-open)")
                r.decr(key)
                return await call_next(request)
            _active_keys.add(key)

            if current > limit:
                r.decr(key)
                _active_keys.discard(key)
                return JSONResponse(
                    status_code=429,
                    content={
                        "code": "concurrency_limit_exceeded",
                        "message": "Too many concurrent requests. Please wait for current requests to complete.",
                    },
                )
        except redis.RedisError:
            logger.warning("Concurrency limit Redis check failed, allowing request (fail-open)")
            return await call_next(request)

        try:
            response = await call_next(request)
            return response
        finally:
            if current is not None:  # ← Only decr if incr succeeded
                try:
                    r.decr(key)
                    _active_keys.discard(key)
                except redis.RedisError:
                    logger.warning("Concurrency limit Redis decrement failed")
