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
      <div className="admin-metric-grid">
        {metrics.map((metric) => (
          <article className="admin-metric-card" key={metric.name}>
            <div className="admin-metric-card__header">
              <strong>{metric.label}</strong>
              <span className={`metric-state metric-state--${metric.status}`}>{metric.status}</span>
            </div>
            <div className="admin-metric-card__values">
              {metric.series.slice(0, 6).map((series, index) => (
                <div className="metric-row" key={`${metric.name}-${index}`}>
                  <span>{labelForSeries(series.labels)}</span>
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

function labelForSeries(labels: Record<string, string>) {
  const preferred = labels.name ?? labels.job ?? labels.status ?? labels.queue ?? labels.path ?? labels.instance;
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
