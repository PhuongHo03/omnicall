import type { MeetingStatus } from "../types/meetingTypes";

type StatusPillProps = {
  status: MeetingStatus;
};

const statusTone: Record<string, string> = {
  DRAFT: "neutral",
  QUEUED: "amber",
  PROCESSING: "amber",
  READY: "green",
  UPLOADED: "blue",
  FAILED: "red"
};

export function StatusPill({ status }: StatusPillProps) {
  return <span className={`status-pill status-pill--${statusTone[status] ?? "neutral"}`}>{status}</span>;
}
