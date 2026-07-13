import unittest

from backend.configs.settings import Settings
from backend.dependencies.auth import CurrentUserContext, require_admin_context
from backend.providers.prometheus_provider import PrometheusSeries, PrometheusTarget
from backend.services.admin_metrics_service import METRIC_QUERIES, AdminMetricsService
from backend.utils.exceptions import ApplicationError


class FakePrometheusProvider:
    def __init__(self) -> None:
        self.query_calls: list[str] = []
        self.target_calls = 0

    def query(self, query: str) -> list[PrometheusSeries]:
        self.query_calls.append(query)
        return []

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
            require_admin_context(CurrentUserContext(user_id="u", role="User"))

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
        self.assertNotIn("up", prometheus.query_calls)
        self.assertEqual(len(cache.writes), 1)
        self.assertEqual(cache.writes[0][2], 10)

    def test_backend_p95_latency_keeps_method_and_path_labels(self) -> None:
        definition = next(item for item in METRIC_QUERIES if item["name"] == "backend_p95_latency")

        self.assertIn("sum by (le, method, path)", definition["query"])

    def test_container_metrics_query_all_project_containers(self) -> None:
        definitions = {
            item["name"]: item["query"]
            for item in METRIC_QUERIES
            if item["name"] in {"container_cpu", "container_memory"}
        }

        self.assertNotIn("topk", definitions["container_cpu"])
        self.assertNotIn("topk", definitions["container_memory"])
        self.assertEqual(
            definitions["container_cpu"],
            'omnicall_docker_container_cpu_cores{compose_project="omnicall"}',
        )
        self.assertEqual(
            definitions["container_memory"],
            'omnicall_docker_container_memory_working_set_bytes{compose_project="omnicall"}',
        )

    def test_infrastructure_metrics_include_operational_coverage(self) -> None:
        definitions = {item["name"]: item["query"] for item in METRIC_QUERIES}

        expected_names = {
            "postgres_connection_states",
            "postgres_db_size",
            "redis_memory",
            "redis_connected_clients",
            "rabbitmq_queue_messages",
            "rabbitmq_consumers",
            "minio_capacity_usable",
            "minio_usage_used",
            "etcd_db_size",
            "milvus_requests",
            "milvus_collections",
            "milvus_stored_rows",
            "nginx_connections",
        }
        self.assertTrue(expected_names.issubset(definitions))
        self.assertNotIn("postgres_connections", definitions)
        self.assertIn("pg_database_size_bytes", definitions["postgres_db_size"])
        self.assertEqual(definitions["rabbitmq_consumers"], "sum(rabbitmq_consumers)")
        self.assertEqual(definitions["minio_usage_used"], "minio_cluster_usage_total_bytes")
        self.assertEqual(definitions["etcd_db_size"], "etcd_mvcc_db_total_size_in_bytes")
        self.assertEqual(definitions["milvus_stored_rows"], "sum(milvus_datacoord_stored_rows_num)")


if __name__ == "__main__":
    unittest.main()
