import threading
from collections.abc import Callable
from uuid import uuid4

from redis import Redis

from backend.configs.settings import Settings, get_settings


class RedisLockProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Redis.from_url(settings.redis_url, decode_responses=True)

    def acquire(self, key: str, ttl_seconds: int | None = None) -> str | None:
        token = str(uuid4())
        locked = self.client.set(
            key,
            token,
            nx=True,
            ex=ttl_seconds or self.settings.redis_processing_lock_ttl_seconds,
        )
        return token if locked else None

    def release(self, key: str, token: str) -> None:
        release_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self.client.eval(release_script, 1, key, token)

    def renew(self, key: str, token: str, ttl_seconds: int | None = None) -> bool:
        """Extend a lock only while ``token`` still owns it.

        Comparing and expiring in one Lua script prevents a delayed worker from
        extending a lock that has already been acquired by another worker.
        """
        renew_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        ttl = max(1, int(ttl_seconds or self.settings.redis_processing_lock_ttl_seconds))
        return bool(self.client.eval(renew_script, 1, key, token, ttl))


class ProcessingLockLostError(RuntimeError):
    """Raised when a long-running worker can no longer prove lock ownership."""


class LockHeartbeat:
    """Keep a token-owned processing lock alive during long synchronous work.

    Older test doubles only implement ``acquire``/``release``. They remain
    compatible: heartbeat becomes a no-op for providers without ``renew``.
    Production Redis locks always use compare-and-expire renewal.
    """

    def __init__(
        self,
        provider: object,
        *,
        key: str,
        token: str,
        ttl_seconds: int,
        interval_seconds: float | None = None,
    ) -> None:
        self.provider = provider
        self.key = key
        self.token = token
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.interval_seconds = (
            max(0.05, min(float(interval_seconds), self.ttl_seconds / 2))
            if interval_seconds is not None
            else max(0.1, min(self.ttl_seconds / 3, 30.0))
        )
        candidate = getattr(provider, "renew", None)
        self._renew: Callable[..., object] | None = candidate if callable(candidate) else None
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def supported(self) -> bool:
        return self._renew is not None

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    def start(self) -> "LockHeartbeat":
        if self._renew is None:
            return self
        self.assert_owned(refresh=True)
        self._thread = threading.Thread(
            target=self._run,
            name=f"lock-heartbeat:{self.key}",
            daemon=True,
        )
        self._thread.start()
        return self

    def assert_owned(self, *, refresh: bool = False) -> None:
        if self._lost.is_set():
            raise ProcessingLockLostError(f"Processing lock ownership was lost: {self.key}")
        if refresh and self._renew is not None and not self._renew_once():
            raise ProcessingLockLostError(f"Processing lock ownership was lost: {self.key}")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2))
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            if not self._renew_once():
                return

    def _renew_once(self) -> bool:
        if self._renew is None:
            return True
        try:
            renewed = bool(
                self._renew(
                    self.key,
                    self.token,
                    ttl_seconds=self.ttl_seconds,
                )
            )
        except Exception:
            renewed = False
        if not renewed:
            self._lost.set()
        return renewed


def get_redis_lock_provider() -> RedisLockProvider:
    return RedisLockProvider(get_settings())
