import time
from collections.abc import Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.models.meeting_models import ChatMessage, Meeting


HTTP_REQUESTS_TOTAL = Counter(
    "omnicall_http_requests_total",
    "HTTP requests handled by the backend.",
    ["method", "path", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "omnicall_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
)
MEETINGS_TOTAL = Gauge(
    "omnicall_meetings_total",
    "Meetings grouped by lifecycle status.",
    ["status"],
)
CHAT_MESSAGES_TOTAL = Gauge(
    "omnicall_chat_messages_total",
    "Chat messages grouped by role.",
    ["role"],
)
CHAT_TURN_TOTAL = Counter(
    "omnicall_chat_turn_total",
    "Durable chat turn lifecycle events.",
    ["event"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)
        started_at = time.perf_counter()
        response = await call_next(request)
        path = _route_path(request)
        status = str(response.status_code)
        HTTP_REQUESTS_TOTAL.labels(request.method, path, status).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(request.method, path).observe(time.perf_counter() - started_at)
        return response


def render_metrics(session: Session) -> Response:
    update_domain_metrics(session)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def update_domain_metrics(session: Session) -> None:
    for status, count in session.execute(select(Meeting.status, func.count()).group_by(Meeting.status)).all():
        MEETINGS_TOTAL.labels(str(status)).set(count)
    for role, count in session.execute(select(ChatMessage.role, func.count()).group_by(ChatMessage.role)).all():
        CHAT_MESSAGES_TOTAL.labels(str(role)).set(count)


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else request.url.path
