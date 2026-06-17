import type { AdminMetric, AdminMetrics, AdminMetricsTarget } from "../types/adminTypes";

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
