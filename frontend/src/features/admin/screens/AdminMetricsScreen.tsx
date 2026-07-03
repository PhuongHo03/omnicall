import { RefreshCw } from "lucide-react";

import { IconButton } from "../../../shared/components/IconButton";
import { PageHeader } from "../../../shared/components/PageHeader";
import { AdminNavbar } from "../components/AdminNavbar";
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
      <AdminNavbar />
      <PageHeader
        title="Operations Metrics"
        subtitle={dashboard.metrics ? new Date(dashboard.metrics.generatedAt).toLocaleString() : "Loading"}
      >
        <IconButton
          icon={<RefreshCw size={16} />}
          label="Refresh"
          disabled={dashboard.isLoading}
          type="button"
          onClick={() => void dashboard.refreshMetrics()}
        />
      </PageHeader>

      <AdminSummaryCards metrics={dashboard.metrics} />
      <AdminTargetsTable targets={dashboard.metrics?.targets ?? []} />

      {dashboard.groupedMetrics.map((group) => (
        <AdminMetricsGroup category={group.category} metrics={group.items} key={group.category} />
      ))}

    </div>
  );
}
