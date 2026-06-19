from datetime import datetime

from pydantic import BaseModel, Field


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


class AdminAccountResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str
    created_at: datetime
    can_change_role: bool


class AdminAccountListResponse(BaseModel):
    items: list[AdminAccountResponse]


class AdminAccountRoleUpdateRequest(BaseModel):
    role: str = Field(pattern="^(Admin|User)$")


class AdminOperationalLogEventResponse(BaseModel):
    id: str
    timestamp: datetime
    level: str
    flow: str
    stage: str
    status: str
    message: str
    workspaceId: str | None = None
    meetingId: str | None = None
    meetingName: str | None = None
    language: str | None = None
    file: dict = Field(default_factory=dict)
    job: dict = Field(default_factory=dict)
    chat: dict = Field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    durationMs: int | None = None
    details: dict = Field(default_factory=dict)
    errorType: str | None = None
    errorMessage: str | None = None


class AdminOperationalLogListResponse(BaseModel):
    items: list[AdminOperationalLogEventResponse]
    limit: int
    retained_limit: int


class AdminOperationalLogClearResponse(BaseModel):
    cleared: bool
