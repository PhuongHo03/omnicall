import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.providers.lock_provider import (
    LockHeartbeat,
    ProcessingLockLostError,
    RedisLockProvider,
)


class ExpiringLockProvider:
    def __init__(self, *, ttl_seconds: int = 1) -> None:
        self.ttl_seconds = ttl_seconds
        self.token = "token"
        self.expires_at = 0.0
        self.renew_enabled = True
        self.renew_count = 0

    def acquire(self, key: str, ttl_seconds: int | None = None) -> str:
        self.expires_at = time.monotonic() + (ttl_seconds or self.ttl_seconds)
        return self.token

    def renew(self, key: str, token: str, ttl_seconds: int | None = None) -> bool:
        if not self.renew_enabled or token != self.token or time.monotonic() >= self.expires_at:
            return False
        self.renew_count += 1
        self.expires_at = time.monotonic() + (ttl_seconds or self.ttl_seconds)
        return True

    def release(self, key: str, token: str) -> None:
        if token == self.token:
            self.expires_at = 0.0

    def owns_lock(self) -> bool:
        return time.monotonic() < self.expires_at


class LegacyFakeLockProvider:
    """Represents existing test/application doubles without ``renew``."""

    def acquire(self, key: str) -> str:
        return "legacy-token"

    def release(self, key: str, token: str) -> None:
        return None


class LockHeartbeatTestCase(unittest.TestCase):
    def test_redis_renew_uses_atomic_compare_and_expire(self) -> None:
        provider = RedisLockProvider.__new__(RedisLockProvider)
        provider.settings = SimpleNamespace(redis_processing_lock_ttl_seconds=90)
        provider.client = MagicMock()
        provider.client.eval.return_value = 1

        self.assertTrue(provider.renew("meeting", "token", ttl_seconds=7))

        script, key_count, key, token, ttl = provider.client.eval.call_args.args
        self.assertIn('redis.call("get", KEYS[1])', script)
        self.assertIn('redis.call("expire", KEYS[1], ARGV[2])', script)
        self.assertEqual((key_count, key, token, ttl), (1, "meeting", "token", 7))

    def test_short_ttl_is_renewed_during_long_work(self) -> None:
        provider = ExpiringLockProvider(ttl_seconds=1)
        token = provider.acquire("meeting", ttl_seconds=1)
        heartbeat = LockHeartbeat(
            provider,
            key="meeting",
            token=token,
            ttl_seconds=1,
            interval_seconds=0.1,
        ).start()
        try:
            time.sleep(1.25)
            heartbeat.assert_owned(refresh=True)
            self.assertTrue(provider.owns_lock())
            self.assertGreaterEqual(provider.renew_count, 3)
        finally:
            heartbeat.stop()
            provider.release("meeting", token)

    def test_lost_token_fences_the_worker(self) -> None:
        provider = ExpiringLockProvider(ttl_seconds=1)
        token = provider.acquire("meeting", ttl_seconds=1)
        heartbeat = LockHeartbeat(
            provider,
            key="meeting",
            token=token,
            ttl_seconds=1,
            interval_seconds=0.05,
        ).start()
        try:
            provider.renew_enabled = False
            deadline = time.monotonic() + 1
            while not heartbeat.lost and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(heartbeat.lost)
            with self.assertRaises(ProcessingLockLostError):
                heartbeat.assert_owned(refresh=True)
        finally:
            heartbeat.stop()

    def test_provider_without_renew_remains_compatible(self) -> None:
        provider = LegacyFakeLockProvider()
        heartbeat = LockHeartbeat(
            provider,
            key="meeting",
            token="legacy-token",
            ttl_seconds=1,
            interval_seconds=0.05,
        ).start()
        try:
            self.assertFalse(heartbeat.supported)
            heartbeat.assert_owned(refresh=True)
        finally:
            heartbeat.stop()


if __name__ == "__main__":
    unittest.main()
