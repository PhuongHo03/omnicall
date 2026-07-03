import { useState } from "react";
import { EmptyState } from "../../../shared/components/EmptyState";
import { useNavigate } from "react-router-dom";

import { ConfirmDialog } from "../../../shared/components/ConfirmDialog";
import { AdminNavbar } from "../components/AdminNavbar";
import { PageHeader } from "../../../shared/components/PageHeader";
import { AdminLogToolbar } from "../components/AdminLogToolbar";
import { AdminMeetingLogCard } from "../components/AdminMeetingLogCard";
import { useAdminMeetingLogs } from "../hooks/useAdminMeetingLogs";

export function AdminLogsScreen({ token }: { token: string }) {
    const navigate = useNavigate();
  const meetingLogs = useAdminMeetingLogs(token);
  const [isClearConfirmationOpen, setIsClearConfirmationOpen] = useState(false);

  return (
    <div className="admin-screen admin-logs-screen">
      <AdminNavbar />
      <PageHeader
        title="Operational Logs"
        subtitle={<>{meetingLogs.filteredMeetings.length} meeting groups · {meetingLogs.autoRefresh ? "live every 2 seconds" : "live paused"}</>}
      />
      <AdminLogToolbar
        mode="list"
        autoRefresh={meetingLogs.autoRefresh}
        isClearing={meetingLogs.isClearing}
        isLoading={meetingLogs.isLoading}
        search={meetingLogs.search}
        onAutoRefreshChange={meetingLogs.setAutoRefresh}
        onClear={() => setIsClearConfirmationOpen(true)}
        onRefresh={() => void meetingLogs.refreshMeetings()}
        onSearchChange={meetingLogs.setSearch}
      />

      <section className="admin-meeting-log-grid">
        {meetingLogs.filteredMeetings.length === 0 ? (
          <EmptyState message="No meeting logs found." />
        ) : (
          meetingLogs.filteredMeetings.map((meeting) => (
            <AdminMeetingLogCard
              key={meeting.meetingId}
              meeting={meeting}
              onClick={(id) => navigate(`/admin/logs/${id}`)}
            />
          ))
        )}
      </section>

      <ConfirmDialog
        confirmLabel="Clear all logs"
        isOpen={isClearConfirmationOpen}
        message="This removes ALL operational log events from Redis for every meeting."
        title="Clear all operational logs?"
        onCancel={() => setIsClearConfirmationOpen(false)}
        onConfirm={() => {
          setIsClearConfirmationOpen(false);
          void meetingLogs.clearAllLogs();
        }}
      />
    </div>
  );
}
