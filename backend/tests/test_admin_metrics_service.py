import unittest

from backend.configs.settings import Settings
from backend.dependencies.auth import CurrentUserContext, require_admin_context
from backend.providers.prometheus_provider import PrometheusSeries, PrometheusTarget
from backend.services.admin_metrics_service import AdminMetricsService
from backend.utils.exceptions import ApplicationError


class FakePrometheusProvider:
    def __init__(self) -> None:
        self.query_calls: list[str] = []
        self.target_calls = 0

    def query(self, query: str) -> list[PrometheusSeries]:
        self.query_calls.append(query)
        return [PrometheusSeries(labels={"job": "backend"}, value=1.0)] if query == "up" else []

    def active_targets(self) -> list[PrometheusTarget]:
        self.target_calls += 1
        return [
            PrometheusTarget(
                job="backend",
                instance="backend:8000",
                health="up",
                scrape_url="http://backend:8000/metrics",
                last_scrape="2026-06-17T00:00:00Z",
                last_error="",
            )
        ]


class FakeCacheProvider:
    def __init__(self, cached: dict | None = None) -> None:
        self.cached = cached
        self.writes: list[tuple[str, dict, int]] = []

    def get_json(self, key: str) -> dict | None:
        return self.cached

    def set_json(self, key: str, value: dict, ttl_seconds: int) -> None:
        self.writes.append((key, value, ttl_seconds))
        self.cached = value


class AdminMetricsServiceTestCase(unittest.TestCase):
    def test_admin_context_requires_owner_or_admin_role(self) -> None:
        with self.assertRaises(ApplicationError) as error:
            require_admin_context(CurrentUserContext(user_id="u", workspace_id="w", role="member"))

        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(error.exception.code, "admin_access_required")

    def test_metrics_are_cached_after_prometheus_fetch(self) -> None:
        prometheus = FakePrometheusProvider()
        cache = FakeCacheProvider()
        service = AdminMetricsService(
            prometheus_provider=prometheus,
            cache_provider=cache,
            settings=Settings(ADMIN_METRICS_CACHE_TTL_SECONDS=10),
        )

        first = service.get_metrics()
        second = service.get_metrics()

        self.assertFalse(first.cache.hit)
        self.assertTrue(second.cache.hit)
        self.assertEqual(prometheus.target_calls, 1)
        self.assertEqual(len(cache.writes), 1)
        self.assertEqual(cache.writes[0][2], 10)


if __name__ == "__main__":
    unittest.main()
