import type {
  AdminAccount,
  AdminAccountList,
  AdminMeetingLogSummary,
  AdminMetric,
  AdminMetrics,
  AdminMetricsTarget,
  AdminOperationalLog,
  AdminOperationalLogList
} from "../types/adminTypes";

type RawMetric = {
  name?: unknown;
  label?: unknown;
  category?: unknown;
  unit?: unknown;
  query?: unknown;
  status?: unknown;
  series?: unknown;
};

type RawTarget = {
  job?: unknown;
  instance?: unknown;
  health?: unknown;
  scrape_url?: unknown;
  last_scrape?: unknown;
  last_error?: unknown;
};

type RawAccount = {
  user_id?: unknown;
  email?: unknown;
  display_name?: unknown;
  role?: unknown;
  created_at?: unknown;
  can_change_role?: unknown;
};

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string") {
    throw new Error(`Invalid ${field}.`);
  }
  return value;
}

function requireNumber(value: unknown, field: string): number {
  if (typeof value !== "number") {
    throw new Error(`Invalid ${field}.`);
  }
  return value;
}

function nullableString(value: unknown, field: string): string | null {
  if (value === null) {
    return null;
  }
  return requireString(value, field);
}

function nullableNumber(value: unknown, field: string): number | null {
  if (value === null) {
    return null;
  }
  return requireNumber(value, field);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function mapTarget(raw: RawTarget): AdminMetricsTarget {
  return {
    job: requireString(raw.job, "target.job"),
    instance: requireString(raw.instance, "target.instance"),
    health: requireString(raw.health, "target.health"),
    scrapeUrl: requireString(raw.scrape_url, "target.scrape_url"),
    lastScrape: nullableString(raw.last_scrape, "target.last_scrape"),
    lastError: requireString(raw.last_error, "target.last_error")
  };
}

function mapMetric(raw: RawMetric): AdminMetric {
  if (!Array.isArray(raw.series)) {
    throw new Error("Invalid metric.series.");
  }
  return {
    name: requireString(raw.name, "metric.name"),
    label: requireString(raw.label, "metric.label"),
    category: requireString(raw.category, "metric.category"),
    unit: requireString(raw.unit, "metric.unit"),
    query: requireString(raw.query, "metric.query"),
    status: requireString(raw.status, "metric.status") as AdminMetric["status"],
    series: raw.series.map((item) => {
      const series = item as { labels?: unknown; value?: unknown };
      return {
        labels: isRecord(series.labels) ? Object.fromEntries(Object.entries(series.labels).map(([key, value]) => [key, String(value)])) : {},
        value: nullableNumber(series.value, "metric.series.value")
      };
    })
  };
}

export function parseAdminMetrics(raw: unknown): AdminMetrics {
  const payload = raw as {
    generated_at?: unknown;
    cache?: unknown;
    summary?: unknown;
    targets?: unknown;
    metrics?: unknown;
  };
  const cache = payload.cache as { hit?: unknown; key?: unknown; ttl_seconds?: unknown };
  const summary = payload.summary as {
    status?: unknown;
    healthy_targets?: unknown;
    total_targets?: unknown;
    degraded_targets?: unknown;
  };
  if (!Array.isArray(payload.targets) || !Array.isArray(payload.metrics)) {
    throw new Error("Invalid admin metrics payload.");
  }
  return {
    generatedAt: requireString(payload.generated_at, "metrics.generated_at"),
    cache: {
      hit: Boolean(cache.hit),
      key: requireString(cache.key, "metrics.cache.key"),
      ttlSeconds: requireNumber(cache.ttl_seconds, "metrics.cache.ttl_seconds")
    },
    summary: {
      status: requireString(summary.status, "metrics.summary.status"),
      healthyTargets: requireNumber(summary.healthy_targets, "metrics.summary.healthy_targets"),
      totalTargets: requireNumber(summary.total_targets, "metrics.summary.total_targets"),
      degradedTargets: requireNumber(summary.degraded_targets, "metrics.summary.degraded_targets")
    },
    targets: payload.targets.map((target) => mapTarget(target as RawTarget)),
    metrics: payload.metrics.map((metric) => mapMetric(metric as RawMetric))
  };
}

export function parseAdminAccount(raw: unknown): AdminAccount {
  const account = raw as RawAccount;
  const role = requireString(account.role, "account.role");
  return {
    userId: requireString(account.user_id, "account.user_id"),
    email: requireString(account.email, "account.email"),
    displayName: requireString(account.display_name, "account.display_name"),
    role: role === "Admin" ? "Admin" : "User",
    createdAt: requireString(account.created_at, "account.created_at"),
    canChangeRole: Boolean(account.can_change_role)
  };
}

export function parseAdminAccounts(raw: unknown): AdminAccountList {
  const payload = raw as { items?: unknown };
  if (!Array.isArray(payload.items)) {
    throw new Error("Invalid admin accounts payload.");
  }
  return {
    items: payload.items.map(parseAdminAccount)
  };
}

export function parseAdminOperationalLogs(raw: unknown): AdminOperationalLogList {
  const payload = raw as {
    items?: unknown;
    limit?: unknown;
    retained_limit?: unknown;
  };
  if (!Array.isArray(payload.items)) {
    throw new Error("Invalid admin operational logs payload.");
  }
  return {
    items: payload.items.map(parseAdminOperationalLog),
    limit: requireNumber(payload.limit, "logs.limit"),
    retainedLimit: requireNumber(payload.retained_limit, "logs.retained_limit")
  };
}

function parseAdminOperationalLog(raw: unknown): AdminOperationalLog {
  if (!isRecord(raw)) {
    throw new Error("Invalid operational log event.");
  }
  const level = requireString(raw.level, "log.level");
  const flow = requireString(raw.flow, "log.flow");
  return {
    id: requireString(raw.id, "log.id"),
    timestamp: requireString(raw.timestamp, "log.timestamp"),
    level: level === "error" ? "error" : "info",
    flow: flow === "rag" ? "rag" : "processing",
    stage: requireString(raw.stage, "log.stage"),
    status: requireString(raw.status, "log.status"),
    message: requireString(raw.message, "log.message"),
    workspaceId: nullableString(raw.workspaceId, "log.workspaceId"),
    meetingId: nullableString(raw.meetingId, "log.meetingId"),
    meetingName: nullableString(raw.meetingName, "log.meetingName"),
    file: isRecord(raw.file) ? raw.file : {},
    chat: isRecord(raw.chat) ? raw.chat : {},
    provider: nullableString(raw.provider, "log.provider"),
    model: nullableString(raw.model, "log.model"),
    durationMs: nullableNumber(raw.durationMs, "log.durationMs"),
    details: isRecord(raw.details) ? raw.details : {},
    errorType: nullableString(raw.errorType, "log.errorType"),
    errorMessage: nullableString(raw.errorMessage, "log.errorMessage")
  };
}

export function parseAdminMeetingLogSummaries(raw: unknown): AdminMeetingLogSummary[] {
  if (!raw || typeof raw !== "object" || !("items" in raw)) {
    return [];
  }
  const items = (raw as Record<string, unknown>).items;
  if (!Array.isArray(items)) {
    return [];
  }
  return items.map((item) => ({
    meetingId: requireString(item.meetingId, "meetingLog.meetingId"),
    meetingName: nullableString(item.meetingName, "meetingLog.meetingName"),
    processingCount: typeof item.processingCount === "number" ? item.processingCount : 0,
    ragCount: typeof item.ragCount === "number" ? item.ragCount : 0,
    latestTimestamp: nullableString(item.latestTimestamp, "meetingLog.latestTimestamp"),
    latestLevel: nullableString(item.latestLevel, "meetingLog.latestLevel"),
  }));
}
