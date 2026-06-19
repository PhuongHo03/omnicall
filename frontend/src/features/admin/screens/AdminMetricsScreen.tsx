import { RefreshCcw } from "lucide-react";

import { AdminMetricsGroup } from "../components/AdminMetricsGroup";
import { AdminSummaryCards } from "../components/AdminSummaryCards";
import { AdminTargetsTable } from "../components/AdminTargetsTable";
import { useAdminMetrics } from "../hooks/useAdminMetrics";

type AdminMetricsScreenProps = {
  token: string;
};

export function AdminMetricsScreen({ token }: AdminMetricsScreenProps) {
  const dashboard = useAdminMetrics(token);

  return (
    <div className="admin-screen">
      <section className="admin-hero">
        <div>
          <h1>Operations Metrics</h1>
          <span>{dashboard.metrics ? new Date(dashboard.metrics.generatedAt).toLocaleString() : "Loading"}</span>
        </div>
        <button
          className="icon-button icon-button--secondary"
          disabled={dashboard.isLoading}
          type="button"
          onClick={() => void dashboard.refreshMetrics()}
        >
          <RefreshCcw size={17} />
          Refresh
        </button>
      </section>

      <AdminSummaryCards metrics={dashboard.metrics} />
      <AdminTargetsTable targets={dashboard.metrics?.targets ?? []} />

      {dashboard.groupedMetrics.map((group) => (
        <AdminMetricsGroup category={group.category} metrics={group.items} key={group.category} />
      ))}

      <div className="event-strip" aria-live="polite">
        <span className={dashboard.error ? "event-strip__error" : ""}>
          {dashboard.error ?? dashboard.notice ?? "Ready"}
        </span>
      </div>
    </div>
  );
}
