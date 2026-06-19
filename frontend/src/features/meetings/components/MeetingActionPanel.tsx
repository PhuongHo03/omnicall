import { Mic, Pause, Play, RefreshCw, RotateCcw, Trash2, Upload } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "../../../shared/components/ConfirmDialog";
import { IconButton } from "../../../shared/components/IconButton";
import type { Meeting, MeetingAsset, ProcessingJob } from "../types/meetingTypes";
import { StatusPill } from "./StatusPill";

type MeetingActionPanelProps = {
  canProcess: boolean;
  canUpload: boolean;
  disabled: boolean;
  hasLockedAsset: boolean;
  isRecording: boolean;
  lastAsset: MeetingAsset | null;
  latestJob: ProcessingJob | null;
  selectedMeeting: Meeting | null;
  showAdminActions: boolean;
  onDeleteMeeting: () => void;
  onFileUpload: (file: File) => void;
  onProcess: () => void;
  onRefreshStatus: () => void;
  onStartRecording: () => void;
  onStopRecording: () => void;
};

export function MeetingActionPanel({
  canProcess,
  canUpload,
  disabled,
  hasLockedAsset,
  isRecording,
  lastAsset,
  latestJob,
  onFileUpload,
  onDeleteMeeting,
  onProcess,
  onRefreshStatus,
  onStartRecording,
  onStopRecording,
  selectedMeeting,
  showAdminActions
}: MeetingActionPanelProps) {
  const canAct = Boolean(selectedMeeting) && !disabled;
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const isRetryAction = latestJob?.retryAllowed === true;
  const statusHint = selectedMeeting ? meetingStatusHint(selectedMeeting) : "Select or create a meeting to begin.";
  const shouldShowIntake = canAct && !hasLockedAsset;

  return (
    <section className="action-panel">
      <div className="detail-header">
        <div>
          <h2>{selectedMeeting?.title ?? "Select a meeting"}</h2>
          <span>{selectedMeeting?.id ?? "No active meeting"}</span>
        </div>
        {selectedMeeting ? <StatusPill status={selectedMeeting.status} /> : null}
      </div>

      {shouldShowIntake ? (
        <div className="intake-box">
          <label className={`file-drop ${canUpload ? "" : "file-drop--disabled"}`}>
            <Upload size={22} />
            <span>Upload</span>
            <input
              type="file"
              accept="audio/*,video/mp4,video/webm,.txt,.md,.vtt,.srt,text/plain,text/markdown,text/vtt,application/x-subrip"
              disabled={!canUpload}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  onFileUpload(file);
                  event.target.value = "";
                }
              }}
            />
          </label>

          <div className="record-controls">
            <IconButton
              icon={<Mic size={16} />}
              label="Record"
              disabled={!canUpload || isRecording}
              onClick={onStartRecording}
              variant="secondary"
            />
            <IconButton
              icon={<Pause size={16} />}
              label="Stop"
              disabled={!isRecording}
              onClick={onStopRecording}
              variant={isRecording ? "danger" : "secondary"}
            />
          </div>
        </div>
      ) : null}

      <div className="process-bar">
        <IconButton
          icon={isRetryAction ? <RotateCcw size={16} /> : <Play size={16} />}
          label={isRetryAction ? "Retry" : "Process"}
          disabled={!canAct || !canProcess}
          onClick={onProcess}
          variant="primary"
        />
        <IconButton
          icon={<RefreshCw size={16} />}
          label="Status"
          disabled={!canAct}
          onClick={onRefreshStatus}
          variant="secondary"
        />
        {showAdminActions ? (
          <IconButton
            icon={<Trash2 size={16} />}
            label="Delete"
            disabled={!canAct}
            onClick={() => setIsDeleteDialogOpen(true)}
            variant="danger"
          />
        ) : null}
      </div>

      <ProcessingProgress meeting={selectedMeeting} asset={lastAsset} latestJob={latestJob} />

      <p className="safe-message">{statusHint}</p>
      {latestJob?.safeFailureReason ? <p className="safe-message">{latestJob.safeFailureReason}</p> : null}
      <ConfirmDialog
        isOpen={isDeleteDialogOpen}
        title="Delete meeting session"
        message={`Delete ${selectedMeeting?.title ?? "this meeting"}? This will delete its uploaded file, processing result, chunks, and chat history.`}
        confirmLabel="Delete session"
        onCancel={() => setIsDeleteDialogOpen(false)}
        onConfirm={() => {
          setIsDeleteDialogOpen(false);
          onDeleteMeeting();
        }}
      />
    </section>
  );
}

function meetingStatusHint(meeting: Meeting) {
  if (meeting.status === "DRAFT") {
    return "Waiting for one meeting file.";
  }
  if (meeting.status === "UPLOADED") {
    return "File is locked for this meeting.";
  }
  if (meeting.status === "FAILED") {
    return "Processing failed. The uploaded file remains locked for retry.";
  }
  if (meeting.status === "QUEUED" || meeting.status === "PROCESSING") {
    return "Processing is running.";
  }
  return "Result is ready.";
}

function ProcessingProgress({
  asset,
  latestJob,
  meeting
}: {
  asset: MeetingAsset | null;
  latestJob: ProcessingJob | null;
  meeting: Meeting | null;
}) {
  const steps = [
    { label: "File", done: Boolean(asset), active: meeting?.status === "UPLOADED" },
    { label: "Queued", done: Boolean(latestJob), active: meeting?.status === "QUEUED" },
    { label: "Processing", done: meeting?.status === "READY", active: meeting?.status === "PROCESSING" },
    { label: "Result", done: meeting?.status === "READY", active: meeting?.status === "READY" }
  ];

  return (
    <div className="progress-panel">
      <div className="progress-panel__topline">
        <strong>{latestJob ? <StatusPill status={latestJob.status} /> : <StatusPill status={meeting?.status ?? "DRAFT"} />}</strong>
        <span>{asset ? asset.fileName : "No file"}</span>
      </div>
      <div className="progress-steps">
        {steps.map((step) => (
          <span
            key={step.label}
            className={[
              "progress-step",
              step.done ? "progress-step--done" : "",
              step.active ? "progress-step--active" : ""
            ].join(" ")}
          >
            {step.label}
          </span>
        ))}
      </div>
    </div>
  );
}
