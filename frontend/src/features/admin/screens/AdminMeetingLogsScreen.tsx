import { useState } from "react";
import { useParams } from "react-router-dom";

import { ConfirmDialog } from "../../../shared/components/ConfirmDialog";
import { AdminNavbar } from "../components/AdminNavbar";
import { PageHeader } from "../../../shared/components/PageHeader";
import { AdminLogDetails } from "../components/AdminLogDetails";
import { AdminLogStream } from "../components/AdminLogStream";
import { AdminLogToolbar } from "../components/AdminLogToolbar";
import { useAdminMeetingLogDetail } from "../hooks/useAdminMeetingLogDetail";
import { useAdminLogs } from "../hooks/useAdminLogs";

export function AdminMeetingLogsScreen({ token }: { token: string }) {
  const { id } = useParams<{ id: string }>();
  const meetingId = id ?? "";
  const logs = useAdminLogs(token, meetingId);
  const [isClearConfirmationOpen, setIsClearConfirmationOpen] = useState(false);
  const detail = useAdminMeetingLogDetail(token, meetingId, logs.isLoading);

  return (
    <div className="admin-screen admin-logs-screen">
      <AdminNavbar />
      <PageHeader
        title={detail.displayName}
        subtitle={logs.autoRefresh ? "live every 2 seconds" : "live paused"}
      />

      <AdminLogToolbar
        mode="detail"
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
            meetingNameOverride={detail.currentMeetingName ?? undefined}
          />
        </div>
        <AdminLogDetails event={logs.selectedEvent} meetingNames={detail.meetingNames} />
      </section>

      <ConfirmDialog
        confirmLabel="Clear meeting logs"
        isOpen={isClearConfirmationOpen}
        message={`This removes all operational log events for ${detail.displayName}.`}
        title="Clear meeting logs?"
        onCancel={() => setIsClearConfirmationOpen(false)}
        onConfirm={() => {
          setIsClearConfirmationOpen(false);
          void logs.clearLogs().then(detail.navigateToLogList);
        }}
      />
    </div>
  );
}
