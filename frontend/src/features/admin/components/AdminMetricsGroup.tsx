import type { AdminMetric } from "../types/adminTypes";

type AdminMetricsGroupProps = {
  category: string;
  metrics: AdminMetric[];
};

export function AdminMetricsGroup({ category, metrics }: AdminMetricsGroupProps) {
  return (
    <section className="admin-panel">
      <div className="panel-heading">
        <h2>{category}</h2>
      </div>
      <div className={metricGridClassName(category, metrics.length)}>
        {metrics.map((metric) => (
          <article className={metricCardClassName(metric.name)} key={metric.name}>
            <div className="admin-metric-card__header">
              <strong>{metric.label}</strong>
              <span className={`metric-state metric-state--${metric.status}`}>{metric.status}</span>
            </div>
            <div className="admin-metric-card__values">
              {metric.series.map((series, index) => (
                <div className="metric-row" key={`${metric.name}-${index}`}>
                  <span>{labelForSeries(metric.name, series.labels)}</span>
                  <strong>{formatValue(series.value, metric.unit)}</strong>
                </div>
              ))}
              {metric.series.length === 0 ? <div className="metric-row metric-row--empty">No data</div> : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

const rowStartMetrics = new Set([
  "postgres_connection_states",
  "redis_memory",
  "rabbitmq_queue_messages",
  "minio_capacity_usable",
  "etcd_db_size",
  "nginx_connections"
]);

function metricGridClassName(category: string, metricCount: number) {
  const classes = ["admin-metric-grid"];
  if (category !== "Infrastructure Services" && metricCount >= 3) {
    classes.push("admin-metric-grid--wide");
  }
  return classes.join(" ");
}

function metricCardClassName(metricName: string) {
  const classes = ["admin-metric-card"];
  if (rowStartMetrics.has(metricName)) {
    classes.push("admin-metric-card--row-start");
  }
  return classes.join(" ");
}

function labelForSeries(metricName: string, labels: Record<string, string>) {
  if (metricName === "backend_request_rate") {
    return [labels.method, labels.path, labels.status].filter(Boolean).join(" · ") || "request";
  }
  if (metricName === "backend_p95_latency") {
    return [labels.method, labels.path].filter(Boolean).join(" · ") || "request";
  }
  if (metricName === "container_cpu" || metricName === "container_memory") {
    return labels.compose_service ?? labels.container_name ?? "container";
  }
  if (metricName === "postgres_connection_states") {
    return labels.state ?? "state";
  }
  if (metricName === "postgres_db_size") {
    return labels.datname ?? "database";
  }
  if (metricName === "rabbitmq_queue_messages") {
    return labels.queue ?? "all queues";
  }
  if (metricName === "redis_memory") {
    return "used memory";
  }
  if (metricName === "redis_connected_clients") {
    return "connected clients";
  }
  if (metricName === "rabbitmq_consumers") {
    return "total consumers";
  }
  if (metricName === "minio_capacity_usable") {
    return "usable capacity";
  }
  if (metricName === "minio_usage_used") {
    return "used by objects";
  }
  if (metricName === "etcd_db_size") {
    return "metadata DB";
  }
  if (metricName === "milvus_requests") {
    return "request rate";
  }
  if (metricName === "milvus_collections") {
    return "collections";
  }
  if (metricName === "milvus_stored_rows") {
    return "stored rows";
  }
  if (metricName === "nginx_connections") {
    return "active connections";
  }

  const preferred = labels.name ?? labels.job ?? labels.queue ?? labels.path ?? labels.status ?? labels.instance;
  if (preferred) {
    return preferred;
  }
  const entries = Object.entries(labels);
  return entries.length > 0 ? entries.map(([key, value]) => `${key}=${value}`).join(", ") : "value";
}

function formatValue(value: number | null, unit: string) {
  if (value === null) {
    return "-";
  }
  if (unit === "bytes") {
    return formatBytes(value);
  }
  if (unit === "req/s" || unit === "cores" || unit === "s") {
    return `${value.toFixed(3)} ${unit}`;
  }
  if (unit === "state") {
    return value >= 1 ? "up" : "down";
  }
  return `${Math.round(value * 100) / 100} ${unit}`;
}

function formatBytes(value: number) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let nextValue = value;
  let unitIndex = 0;
  while (nextValue >= 1024 && unitIndex < units.length - 1) {
    nextValue /= 1024;
    unitIndex += 1;
  }
  return `${nextValue.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}
