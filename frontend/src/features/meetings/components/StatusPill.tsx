import type { MeetingStatus, ProcessingJobStatus } from "../types/meetingTypes";

type StatusPillProps = {
  status: MeetingStatus | ProcessingJobStatus;
};

const statusTone: Record<string, string> = {
  DRAFT: "neutral",
  UPLOADED: "teal",
  QUEUED: "indigo",
  PROCESSING: "amber",
  READY: "green",
  FAILED: "red",
  PENDING: "indigo",
  RUNNING: "amber",
  RETRYING: "amber",
  SUCCEEDED: "green",
  CANCELLED: "neutral"
};

export function StatusPill({ status }: StatusPillProps) {
  return <span className={`status-pill status-pill--${statusTone[status] ?? "neutral"}`}>{status}</span>;
}
