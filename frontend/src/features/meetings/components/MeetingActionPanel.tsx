import { Mic, Pause, Play, RefreshCw, RotateCcw, Upload } from "lucide-react";

import { IconButton } from "../../../components/IconButton";
import type { Meeting, MeetingAsset, ProcessingJob } from "../types/meetingTypes";
import { StatusPill } from "./StatusPill";

type MeetingActionPanelProps = {
  disabled: boolean;
  isRecording: boolean;
  lastAsset: MeetingAsset | null;
  latestJob: ProcessingJob | null;
  selectedMeeting: Meeting | null;
  onFileUpload: (file: File) => void;
  onProcess: () => void;
  onRefreshStatus: () => void;
  onStartRecording: () => void;
  onStopRecording: () => void;
};

export function MeetingActionPanel({
  disabled,
  isRecording,
  lastAsset,
  latestJob,
  onFileUpload,
  onProcess,
  onRefreshStatus,
  onStartRecording,
  onStopRecording,
  selectedMeeting
}: MeetingActionPanelProps) {
  const canAct = Boolean(selectedMeeting) && !disabled;
  const isRetryAction = latestJob?.retryAllowed === true;

  return (
    <section className="detail-panel">
      <div className="detail-header">
        <div>
          <h2>{selectedMeeting?.title ?? "Select a meeting"}</h2>
          <span>{selectedMeeting?.id ?? "No active meeting"}</span>
        </div>
        {selectedMeeting ? <StatusPill status={selectedMeeting.status} /> : null}
      </div>

      <div className="action-grid">
        <label className={`file-drop ${canAct ? "" : "file-drop--disabled"}`}>
          <Upload size={22} />
          <span>Upload audio, video, or transcript</span>
          <input
            type="file"
            accept="audio/*,video/mp4,video/webm,.txt,.md,.vtt,.srt,text/plain,text/markdown,text/vtt,application/x-subrip"
            disabled={!canAct}
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
            disabled={!canAct || isRecording}
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

        <div className="process-controls">
          <IconButton
            icon={isRetryAction ? <RotateCcw size={16} /> : <Play size={16} />}
            label={isRetryAction ? "Retry" : "Process"}
            disabled={!canAct}
            onClick={onProcess}
            variant="primary"
          />
          <IconButton
            icon={<RefreshCw size={16} />}
            label="Status"
            disabled={!canAct}
            onClick={onRefreshStatus}
          />
        </div>
      </div>

      <div className="status-grid">
        <div>
          <span>Last asset</span>
          <strong>{lastAsset ? lastAsset.fileName : "None"}</strong>
        </div>
        <div>
          <span>Latest job</span>
          <strong>{latestJob ? <StatusPill status={latestJob.status} /> : "None"}</strong>
        </div>
        <div>
          <span>Retry</span>
          <strong>{latestJob?.retryAllowed ? "Allowed" : "Unavailable"}</strong>
        </div>
      </div>

      {latestJob?.safeFailureReason ? <p className="safe-message">{latestJob.safeFailureReason}</p> : null}
    </section>
  );
}
