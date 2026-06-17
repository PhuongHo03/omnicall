from datetime import UTC, datetime
from typing import Any

from backend.configs.settings import Settings, get_settings
from backend.dtos.admin_dto import (
    AdminMetricResponse,
    AdminMetricsCacheResponse,
    AdminMetricsResponse,
    AdminMetricsSummaryResponse,
    AdminMetricsTargetResponse,
    AdminMetricSeriesResponse,
)
from backend.providers.cache_provider import CacheProviderError, JsonCacheProvider, get_json_cache_provider
from backend.providers.prometheus_provider import (
    PrometheusProvider,
    PrometheusProviderError,
    PrometheusSeries,
    PrometheusTarget,
    get_prometheus_provider,
)


METRIC_QUERIES = [
    {
        "name": "target_up",
        "label": "Scrape target availability",
        "category": "targets",
        "unit": "state",
        "query": "up",
    },
    {
        "name": "backend_request_rate",
        "label": "Backend request rate",
        "category": "backend",
        "unit": "req/s",
        "query": "sum by (method, path, status) (rate(omnicall_http_requests_total[5m]))",
    },
    {
        "name": "backend_p95_latency",
        "label": "Backend p95 latency",
        "category": "backend",
        "unit": "s",
        "query": "histogram_quantile(0.95, sum by (le, path) (rate(omnicall_http_request_duration_seconds_bucket[5m])))",
    },
    {
        "name": "meetings_by_status",
        "label": "Meetings by status",
        "category": "application",
        "unit": "count",
        "query": "sum by (status) (omnicall_meetings_total)",
    },
    {
        "name": "processing_jobs_by_status",
        "label": "Processing jobs by status",
        "category": "worker",
        "unit": "count",
        "query": "sum by (status) (omnicall_processing_jobs_total)",
    },
    {
        "name": "chat_messages_by_role",
        "label": "Chat messages by role",
        "category": "application",
        "unit": "count",
        "query": "sum by (role) (omnicall_chat_messages_total)",
    },
    {
        "name": "container_cpu",
        "label": "Container CPU",
        "category": "containers",
        "unit": "cores",
        "query": 'topk(10, omnicall_docker_container_cpu_cores{compose_project="omnicall"})',
    },
    {
        "name": "container_memory",
        "label": "Container memory",
        "category": "containers",
        "unit": "bytes",
        "query": 'topk(10, omnicall_docker_container_memory_working_set_bytes{compose_project="omnicall"})',
    },
    {
        "name": "postgres_connections",
        "label": "PostgreSQL connections",
        "category": "database",
        "unit": "count",
        "query": "sum(pg_stat_activity_count)",
    },
    {
        "name": "redis_memory",
        "label": "Redis memory used",
        "category": "cache",
        "unit": "bytes",
        "query": "redis_memory_used_bytes",
    },
    {
        "name": "rabbitmq_queue_messages",
        "label": "RabbitMQ queued messages",
        "category": "queue",
        "unit": "count",
        "query": "sum by (queue) (rabbitmq_queue_messages)",
    },
    {
        "name": "minio_capacity_usable",
        "label": "MinIO usable capacity",
        "category": "storage",
        "unit": "bytes",
        "query": "minio_cluster_capacity_usable_total_bytes",
    },
    {
        "name": "milvus_requests",
        "label": "Milvus request rate",
        "category": "vector",
        "unit": "req/s",
        "query": "sum(rate(milvus_proxy_req_count[5m]))",
    },
    {
        "name": "nginx_connections",
        "label": "NGINX active connections",
        "category": "gateway",
        "unit": "count",
        "query": "nginx_connections_active",
    },
]


class AdminMetricsService:
    def __init__(
        self,
        *,
        prometheus_provider: PrometheusProvider | None = None,
        cache_provider: JsonCacheProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.prometheus_provider = prometheus_provider or get_prometheus_provider()
        self.cache_provider = cache_provider or get_json_cache_provider()

    def get_metrics(self) -> AdminMetricsResponse:
        cached = self._read_cache()
        if cached is not None:
            cached["cache"] = {
                "hit": True,
                "key": self.settings.admin_metrics_cache_key,
                "ttl_seconds": self.settings.admin_metrics_cache_ttl_seconds,
            }
            return AdminMetricsResponse.model_validate(cached)

        response = self._build_response(cache_hit=False)
        self._write_cache(response)
        return response

    def _build_response(self, *, cache_hit: bool) -> AdminMetricsResponse:
        targets = self._load_targets()
        metrics = [self._load_metric(definition) for definition in METRIC_QUERIES]
        healthy_targets = sum(1 for target in targets if target.health == "up")
        degraded_targets = max(0, len(targets) - healthy_targets)
        status = "healthy" if targets and degraded_targets == 0 else "degraded"
        if not targets:
            status = "unavailable"
        return AdminMetricsResponse(
            generated_at=datetime.now(UTC),
            cache=AdminMetricsCacheResponse(
                hit=cache_hit,
                key=self.settings.admin_metrics_cache_key,
                ttl_seconds=self.settings.admin_metrics_cache_ttl_seconds,
            ),
            summary=AdminMetricsSummaryResponse(
                status=status,
                healthy_targets=healthy_targets,
                total_targets=len(targets),
                degraded_targets=degraded_targets,
            ),
            targets=[_target_response(target) for target in targets],
            metrics=metrics,
        )

    def _load_targets(self) -> list[PrometheusTarget]:
        try:
            return self.prometheus_provider.active_targets()
        except PrometheusProviderError:
            return []

    def _load_metric(self, definition: dict[str, str]) -> AdminMetricResponse:
        try:
            series = self.prometheus_provider.query(definition["query"])
            status = "ok" if series else "no_data"
        except PrometheusProviderError:
            series = []
            status = "unavailable"
        return AdminMetricResponse(
            name=definition["name"],
            label=definition["label"],
            category=definition["category"],
            unit=definition["unit"],
            query=definition["query"],
            status=status,
            series=[_series_response(item) for item in series],
        )

    def _read_cache(self) -> dict[str, Any] | None:
        try:
            return self.cache_provider.get_json(self.settings.admin_metrics_cache_key)
        except CacheProviderError:
            return None

    def _write_cache(self, response: AdminMetricsResponse) -> None:
        payload = response.model_dump(mode="json")
        payload["cache"]["hit"] = False
        try:
            self.cache_provider.set_json(
                self.settings.admin_metrics_cache_key,
                payload,
                self.settings.admin_metrics_cache_ttl_seconds,
            )
        except CacheProviderError:
            return


def _series_response(series: PrometheusSeries) -> AdminMetricSeriesResponse:
    return AdminMetricSeriesResponse(labels=series.labels, value=series.value)


def _target_response(target: PrometheusTarget) -> AdminMetricsTargetResponse:
    return AdminMetricsTargetResponse(
        job=target.job,
        instance=target.instance,
        health=target.health,
        scrape_url=target.scrape_url,
        last_scrape=target.last_scrape,
        last_error=target.last_error,
    )


def get_admin_metrics_service() -> AdminMetricsService:
    return AdminMetricsService()
