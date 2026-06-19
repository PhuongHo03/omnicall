import { useState } from "react";

import { ConfirmDialog } from "../../../shared/components/ConfirmDialog";
import { AdminLogDetails } from "../components/AdminLogDetails";
import { AdminLogStream } from "../components/AdminLogStream";
import { AdminLogToolbar } from "../components/AdminLogToolbar";
import { useAdminLogs } from "../hooks/useAdminLogs";

export function AdminLogsScreen({ token }: { token: string }) {
  const logs = useAdminLogs(token);
  const [isClearConfirmationOpen, setIsClearConfirmationOpen] = useState(false);

  return (
    <div className="admin-screen admin-logs-screen">
      <section className="admin-hero">
        <div>
          <h1>Operational Logs</h1>
          <span>
            Redis tail stream · retaining up to {logs.retainedLimit} events · {logs.autoRefresh ? "live every 2 seconds" : "live paused"}
          </span>
        </div>
      </section>

      <AdminLogToolbar
        autoRefresh={logs.autoRefresh}
        flow={logs.flow}
        isClearing={logs.isClearing}
        isLoading={logs.isLoading}
        level={logs.level}
        limit={logs.limit}
        search={logs.search}
        onAutoRefreshChange={logs.setAutoRefresh}
        onClear={() => setIsClearConfirmationOpen(true)}
        onFlowChange={logs.setFlow}
        onLevelChange={logs.setLevel}
        onLimitChange={logs.setLimit}
        onRefresh={() => void logs.refreshLogs()}
        onSearchChange={logs.setSearch}
      />

      <section className="admin-log-workspace">
        <div className="admin-log-stream-panel">
          <div className="admin-log-stream-panel__heading">
            <strong>{logs.flow === "rag" ? "RAG Chat Logs" : "Processing Logs"}</strong>
            <span>{logs.logs.length} events</span>
          </div>
          <AdminLogStream
            logs={logs.logs}
            selectedEventId={logs.selectedEventId}
            onSelect={logs.setSelectedEventId}
          />
        </div>
        <AdminLogDetails event={logs.selectedEvent} />
      </section>

      <div className="event-strip" aria-live="polite">
        <span className={logs.error ? "event-strip__error" : ""}>
          {logs.error ?? logs.notice ?? "Ready"}
        </span>
      </div>

      <ConfirmDialog
        confirmLabel="Clear logs"
        isOpen={isClearConfirmationOpen}
        message="This removes the current temporary processing and RAG event stream from Redis."
        title="Clear operational logs?"
        onCancel={() => setIsClearConfirmationOpen(false)}
        onConfirm={() => {
          setIsClearConfirmationOpen(false);
          void logs.clearLogs();
        }}
      />
    </div>
  );
}
