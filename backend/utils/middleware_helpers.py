"""Shared utilities for middleware route matching and client identification."""
import hashlib
from typing import Optional

from starlette.requests import Request


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For header."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hash_client_id(value: str) -> str:
    """Hash a client identifier (IP, auth token, user ID) to fixed-length digest."""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def identify_client_for_rate_limit(request: Request, group: str = "") -> str:
    """Identify client for rate-limiting: by auth token or IP (public endpoints always by IP)."""
    if group == "public":
        # Public endpoints always use IP-based identification
        ip = get_client_ip(request)
        return hash_client_id(ip)

    # Authenticated endpoints prefer auth token
    auth = request.headers.get("authorization", "")
    if auth:
        return hash_client_id(auth)

    # Fallback to IP
    ip = get_client_ip(request)
    return hash_client_id(ip)


def identify_account_for_concurrency(request: Request) -> str:
    """Identify account for concurrency limiting: by auth token → user ID → IP."""
    # Try auth token first (strongest identifier)
    auth = request.headers.get("authorization", "")
    if auth:
        return hash_client_id(auth)

    # Try development user ID header
    user_id = request.headers.get("x-user-id", "")
    if user_id:
        return hash_client_id(user_id)

    # Fallback to IP
    ip = get_client_ip(request)
    return hash_client_id(ip)


def match_route_group(request: Request, route_groups: list[tuple[str, str]]) -> Optional[str]:
    """Match request to route group by method + path prefix.

    Args:
        request: Starlette request
        route_groups: List of ("METHOD /path/prefix", "group_name") tuples

    Returns:
        Group name if matched, None otherwise
    """
    method = request.method
    path = request.url.path
    for prefix, group in route_groups:
        prefix_method, prefix_path = prefix.split(" ", 1)
        if method == prefix_method and path.startswith(prefix_path):
            return group
    return None
