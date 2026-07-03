import { Activity, Database, RefreshCw, Server } from "lucide-react";

import type { AdminMetrics } from "../types/adminTypes";

type AdminSummaryCardsProps = {
  metrics: AdminMetrics | null;
};

export function AdminSummaryCards({ metrics }: AdminSummaryCardsProps) {
  return (
    <div className="admin-summary-grid">
      <article className="admin-summary-card">
        <Server size={18} />
        <span>Status</span>
        <strong>{metrics?.summary.status ?? "Loading"}</strong>
      </article>
      <article className="admin-summary-card">
        <Activity size={18} />
        <span>Targets</span>
        <strong>
          {metrics ? `${metrics.summary.healthyTargets}/${metrics.summary.totalTargets}` : "-"}
        </strong>
      </article>
      <article className="admin-summary-card">
        <Database size={18} />
        <span>Cache</span>
        <strong>{metrics?.cache.hit ? "Hit" : "Fresh"}</strong>
      </article>
      <article className="admin-summary-card">
        <RefreshCw size={18} />
        <span>TTL</span>
        <strong>{metrics ? `${metrics.cache.ttlSeconds}s` : "-"}</strong>
      </article>
    </div>
  );
}
