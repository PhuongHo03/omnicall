import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.configs.settings import Settings, get_settings


class PrometheusProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class PrometheusSeries:
    labels: dict[str, str]
    value: float | None


@dataclass(frozen=True)
class PrometheusTarget:
    job: str
    instance: str
    health: str
    scrape_url: str
    last_scrape: str | None
    last_error: str


class PrometheusProvider:
    def query(self, query: str) -> list[PrometheusSeries]:
        raise NotImplementedError

    def active_targets(self) -> list[PrometheusTarget]:
        raise NotImplementedError


class HttpPrometheusProvider(PrometheusProvider):
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.prometheus_url.rstrip("/")

    def query(self, query: str) -> list[PrometheusSeries]:
        payload = self._get_json(f"/api/v1/query?{urlencode({'query': query})}")
        if payload.get("status") != "success":
            raise PrometheusProviderError("Prometheus query failed.")
        result = payload.get("data", {}).get("result", [])
        if not isinstance(result, list):
            raise PrometheusProviderError("Prometheus query result was malformed.")
        return [_series_from_result(item) for item in result if isinstance(item, dict)]

    def active_targets(self) -> list[PrometheusTarget]:
        payload = self._get_json("/api/v1/targets?state=active")
        if payload.get("status") != "success":
            raise PrometheusProviderError("Prometheus targets request failed.")
        active_targets = payload.get("data", {}).get("activeTargets", [])
        if not isinstance(active_targets, list):
            raise PrometheusProviderError("Prometheus targets result was malformed.")
        return [_target_from_result(item) for item in active_targets if isinstance(item, dict)]

    def _get_json(self, path: str) -> dict[str, Any]:
        try:
            with urlopen(f"{self.base_url}{path}", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PrometheusProviderError("Prometheus request failed.") from exc
        return payload if isinstance(payload, dict) else {}


def _series_from_result(item: dict) -> PrometheusSeries:
    metric = item.get("metric", {})
    labels = {str(key): str(value) for key, value in metric.items()} if isinstance(metric, dict) else {}
    value = item.get("value", [])
    numeric_value: float | None = None
    if isinstance(value, list) and len(value) >= 2:
        try:
            numeric_value = float(value[1])
        except (TypeError, ValueError):
            numeric_value = None
    return PrometheusSeries(labels=labels, value=numeric_value)


def _target_from_result(item: dict) -> PrometheusTarget:
    labels = item.get("labels", {})
    discovered_labels = item.get("discoveredLabels", {})
    job = _label_value(labels, "job") or _label_value(discovered_labels, "__meta_docker_container_label_com_docker_compose_service") or "unknown"
    instance = _label_value(labels, "instance") or _label_value(discovered_labels, "__address__") or "unknown"
    return PrometheusTarget(
        job=job,
        instance=instance,
        health=str(item.get("health", "unknown")),
        scrape_url=str(item.get("scrapeUrl", "")),
        last_scrape=item.get("lastScrape") if isinstance(item.get("lastScrape"), str) else None,
        last_error=str(item.get("lastError", "")),
    )


def _label_value(labels: Any, key: str) -> str | None:
    if isinstance(labels, dict):
        value = labels.get(key)
        return str(value) if value is not None else None
    return None


def get_prometheus_provider() -> PrometheusProvider:
    return HttpPrometheusProvider(get_settings())
