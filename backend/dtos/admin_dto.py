from datetime import datetime

from pydantic import BaseModel


class AdminMetricsCacheResponse(BaseModel):
    hit: bool
    key: str
    ttl_seconds: int


class AdminMetricsSummaryResponse(BaseModel):
    status: str
    healthy_targets: int
    total_targets: int
    degraded_targets: int


class AdminMetricSeriesResponse(BaseModel):
    labels: dict[str, str]
    value: float | None


class AdminMetricResponse(BaseModel):
    name: str
    label: str
    category: str
    unit: str
    query: str
    status: str
    series: list[AdminMetricSeriesResponse]


class AdminMetricsTargetResponse(BaseModel):
    job: str
    instance: str
    health: str
    scrape_url: str
    last_scrape: str | None
    last_error: str


class AdminMetricsResponse(BaseModel):
    generated_at: datetime
    cache: AdminMetricsCacheResponse
    summary: AdminMetricsSummaryResponse
    targets: list[AdminMetricsTargetResponse]
    metrics: list[AdminMetricResponse]
