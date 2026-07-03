import { AlertTriangle, FileText, MessageSquare } from "lucide-react";

import type { AdminMeetingLogSummary } from "../types/adminTypes";

type AdminMeetingLogCardProps = {
  meeting: AdminMeetingLogSummary;
  onClick: (meetingId: string) => void;
};

export function AdminMeetingLogCard({ meeting, onClick }: AdminMeetingLogCardProps) {
  const hasError = meeting.latestLevel === "error";
  const totalLogs = meeting.processingCount + meeting.ragCount;

  return (
    <button
      className={`admin-meeting-log-card${hasError ? " admin-meeting-log-card--error" : ""}`}
      type="button"
      onClick={() => onClick(meeting.meetingId)}
    >
      <div className="admin-meeting-log-card__header">
        <span className="admin-meeting-log-card__name">
          {meeting.meetingName || meeting.meetingId.slice(0, 8)}
        </span>
        {hasError && <AlertTriangle size={14} className="admin-meeting-log-card__error-icon" />}
      </div>
      <div className="admin-meeting-log-card__stats">
        <span className="admin-meeting-log-card__stat">
          <FileText size={13} />
          {meeting.processingCount}
        </span>
        <span className="admin-meeting-log-card__stat">
          <MessageSquare size={13} />
          {meeting.ragCount}
        </span>
      </div>
      <div className="admin-meeting-log-card__footer">
        <span className="admin-meeting-log-card__count">{totalLogs} events</span>
        {meeting.latestTimestamp && (
          <span className="admin-meeting-log-card__time">
            {new Date(meeting.latestTimestamp).toLocaleTimeString()}
          </span>
        )}
      </div>
    </button>
  );
}
