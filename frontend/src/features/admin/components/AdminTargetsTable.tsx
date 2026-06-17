import type { AdminMetricsTarget } from "../types/adminTypes";

type AdminTargetsTableProps = {
  targets: AdminMetricsTarget[];
};

export function AdminTargetsTable({ targets }: AdminTargetsTableProps) {
  return (
    <section className="admin-panel">
      <div className="panel-heading">
        <h2>Prometheus Targets</h2>
      </div>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Job</th>
              <th>Instance</th>
              <th>Health</th>
              <th>Last Scrape</th>
            </tr>
          </thead>
          <tbody>
            {targets.map((target) => (
              <tr key={`${target.job}:${target.instance}`}>
                <td>{target.job}</td>
                <td>{target.instance}</td>
                <td>
                  <span className={`target-health target-health--${target.health}`}>
                    {target.health}
                  </span>
                </td>
                <td>{target.lastScrape ? new Date(target.lastScrape).toLocaleString() : "-"}</td>
              </tr>
            ))}
            {targets.length === 0 ? (
              <tr>
                <td colSpan={4}>No targets reported.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
