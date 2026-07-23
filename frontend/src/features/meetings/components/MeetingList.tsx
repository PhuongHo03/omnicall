import type { Meeting } from "../types/meetingTypes";
import { EmptyState } from "../../../shared/components/EmptyState";

type MeetingListProps = {
  disabled: boolean;
  meetings: Meeting[];
  selectedMeetingId: string | null;
  onCreate: () => void;
  onSelect: (meetingId: string | null) => void;
};

function statusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (["draft", "uploaded", "queued", "processing", "ready", "failed"].includes(normalized)) {
    return normalized;
  }
  return "draft";
}

export function MeetingList({ disabled, meetings, selectedMeetingId, onSelect }: MeetingListProps) {
  if (meetings.length === 0) {
    return (
      <EmptyState message="No meetings yet." />
    );
  }

  return (
    <div className="meeting-list">
      {meetings.map((meeting) => (
        <button
          key={meeting.id}
          className={`meeting-card-sidebar${meeting.id === selectedMeetingId ? " active" : ""}`}
          type="button"
          disabled={disabled && meeting.id !== selectedMeetingId}
          onClick={() => onSelect(meeting.id)}
        >
          <span className={`status-dot status-dot--${statusClass(meeting.status)}`} />
          <span className="meeting-card-sidebar-title">{meeting.title}</span>
        </button>
      ))}
    </div>
  );
}
