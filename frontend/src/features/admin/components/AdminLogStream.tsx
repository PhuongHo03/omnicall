import { AlertCircle, Bot, CheckCircle2, FileAudio, Workflow } from "lucide-react";

import type { AdminOperationalLog } from "../types/adminTypes";

type AdminLogStreamProps = {
  logs: AdminOperationalLog[];
  selectedEventId: string | null;
  onSelect: (eventId: string) => void;
};

export function AdminLogStream({ logs, selectedEventId, onSelect }: AdminLogStreamProps) {
  if (!logs.length) {
    return <div className="admin-log-empty">No matching operational events.</div>;
  }

  return (
    <div className="admin-log-stream" role="list">
      {logs.map((event) => {
        const fileName = stringValue(event.file.name);
        const question = stringValue(event.chat.questionPreview);
        const isSelected = selectedEventId === event.id;
        const FlowIcon = event.flow === "rag" ? Bot : Workflow;
        const LevelIcon = event.level === "error" ? AlertCircle : CheckCircle2;
        return (
          <button
            className={isSelected ? "admin-log-event admin-log-event--selected" : "admin-log-event"}
            key={event.id}
            type="button"
            role="listitem"
            onClick={() => onSelect(event.id)}
          >
            <div className="admin-log-event__rail">
              <LevelIcon size={16} />
              <span />
            </div>
            <div className="admin-log-event__body">
              <div className="admin-log-event__topline">
                <span className={`admin-log-level admin-log-level--${event.level}`}>{event.level}</span>
                <strong>{formatStage(event.stage)}</strong>
                <span>{event.status}</span>
                <time>{formatTime(event.timestamp)}</time>
              </div>
              <p>{event.message}</p>
              <div className="admin-log-event__identity">
                <span>
                  <FlowIcon size={13} />
                  {event.meetingName ?? event.meetingId ?? "System"}
                </span>
                {fileName ? (
                  <span>
                    <FileAudio size={13} />
                    {fileName}
                  </span>
                ) : null}
              </div>
              {question ? <blockquote>{question}</blockquote> : null}
              <div className="admin-log-event__technical">
                {event.provider ? <span>Provider: {event.provider}</span> : null}
                {event.model ? <span>Model: {event.model}</span> : null}
                {event.durationMs !== null ? <span>{formatDuration(event.durationMs)}</span> : null}
                {event.errorType ? <span>Error: {event.errorType}</span> : null}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function formatStage(stage: string) {
  return stage
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatTime(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatDuration(value: number) {
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value} ms`;
}
