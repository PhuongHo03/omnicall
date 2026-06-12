import { RefreshCw } from "lucide-react";

import { IconButton } from "../../../components/IconButton";
import type { Meeting } from "../types/meetingTypes";
import { StatusPill } from "./StatusPill";

type MeetingListProps = {
  disabled: boolean;
  meetings: Meeting[];
  selectedMeetingId: string | null;
  onRefresh: () => void;
  onSelect: (meetingId: string) => void;
};

export function MeetingList({ disabled, meetings, onRefresh, onSelect, selectedMeetingId }: MeetingListProps) {
  return (
    <section className="list-panel">
      <div className="panel-heading panel-heading--with-action">
        <h2>Meetings</h2>
        <IconButton icon={<RefreshCw size={16} />} label="Refresh" disabled={disabled} onClick={onRefresh} />
      </div>
      <div className="meeting-list">
        {meetings.length === 0 ? (
          <div className="empty-panel">No meetings in this workspace.</div>
        ) : (
          meetings.map((meeting) => (
            <button
              key={meeting.id}
              className={`meeting-card ${meeting.id === selectedMeetingId ? "meeting-card--active" : ""}`}
              onClick={() => onSelect(meeting.id)}
            >
              <span className="meeting-card__title">{meeting.title}</span>
              <span className="meeting-card__meta">
                <StatusPill status={meeting.status} />
                <span>{meeting.language ?? "auto"}</span>
              </span>
            </button>
          ))
        )}
      </div>
    </section>
  );
}
