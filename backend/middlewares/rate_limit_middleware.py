import logging
import time

import redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.configs.settings import get_settings
from backend.providers.redis_provider import get_redis_client
from backend.utils.middleware_helpers import identify_client_for_rate_limit, match_route_group

logger = logging.getLogger(__name__)

_ROUTE_GROUPS: list[tuple[str, str]] = [
    ("POST /api/auth/register", "public"),
    ("POST /api/auth/", "auth"),
    ("GET /api/meetings", "meetings"),
    ("GET /api/me", "meetings"),
    ("POST /api/meetings", "meetings"),
    ("PATCH /api/meetings", "meetings"),
    ("DELETE /api/meetings", "meetings"),
    ("GET /api/admin/", "admin"),
    ("POST /api/admin/", "admin"),
    ("PATCH /api/admin/", "admin"),
    ("DELETE /api/admin/", "admin"),
]

_memory_counters: dict[str, list[float]] = {}


def _memory_rate_check(key: str, quota: int) -> bool:
    """In-memory sliding-window rate check. Returns True if within quota."""
    now = time.time()
    entries = _memory_counters.setdefault(key, [])
    entries[:] = [ts for ts in entries if ts > now - 60]
    if not entries:
        _memory_counters[key] = entries
    entries.append(now)
    return len(entries) <= quota


def _quota_for_group(group: str, settings) -> int:
    if group == "public":
        return settings.rate_limit_public_per_minute
    if group == "auth":
        return settings.rate_limit_auth_per_minute
    if group == "meetings":
        return settings.rate_limit_meetings_per_minute
    if group == "admin":
        return settings.rate_limit_admin_per_minute
    return 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return await call_next(request)

        group = match_route_group(request, _ROUTE_GROUPS)
        if group is None:
            return await call_next(request)

        client_hash = identify_client_for_rate_limit(request, group)
        key = f"ratelimit:{group}:{client_hash}"
        quota = _quota_for_group(group, settings)
        count = 0

        try:
            r = get_redis_client()
            pipe = r.pipeline()
            pipe.zadd(key, {str(time.time()): time.time()})
            pipe.zremrangebyscore(key, 0, time.time() - 60)
            pipe.zcard(key)
            pipe.expire(key, 120)
            _, _, count, _ = pipe.execute()

            if count > quota:
                retry_after = 60 - (int(time.time()) % 60)
                return JSONResponse(
                    status_code=429,
                    content={"code": "rate_limit_exceeded", "message": "Too many requests. Please try again later."},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(quota),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + 60),
                    },
                )
        except redis.RedisError:
            logger.warning("Rate limit Redis failed, falling back to in-memory")
            if not _memory_rate_check(key, quota):
                retry_after = 60 - (int(time.time()) % 60)
                return JSONResponse(
                    status_code=429,
                    content={"code": "rate_limit_exceeded", "message": "Too many requests. Please try again later."},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(quota),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + 60),
                    },
                )
            now = time.time()
            entries = _memory_counters.get(key, [])
            count = len([ts for ts in entries if ts > now - 60])

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(quota)
        response.headers["X-RateLimit-Remaining"] = str(max(0, quota - count))
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)
        return response
