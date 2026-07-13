import { Braces, Check, Mic, Pause, Pencil, Play, RefreshCw, RotateCcw, Trash2, Upload, Volume2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ConfirmDialog } from "../../../shared/components/ConfirmDialog";
import { IconButton } from "../../../shared/components/IconButton";
import { IconOnlyButton } from "../../../shared/components/IconOnlyButton";
import type { Meeting } from "../types/meetingTypes";
import { StatusPill } from "./StatusPill";

type MeetingActionPanelProps = {
  canProcess: boolean;
  canUpload: boolean;
  canViewResult: boolean;
  hasAsset: boolean;
  isProcessing?: boolean;
  isRefreshingStatus?: boolean;
  isUploading?: boolean;
  isRecording: boolean;
  selectedMeeting: Meeting;
  onDeleteMeeting: () => void;
  onFileUpload: (file: File) => void;
  onProcess: () => void;
  onRefreshStatus: () => void;
  onRefreshHistory: () => void;
  onRenameMeeting: (title: string) => void;
  onStartRecording: () => void;
  onStopRecording: () => void;
  onOpenPlayback: () => void;
  onViewResult: () => void;
};

export function MeetingActionPanel({
  canProcess,
  canUpload,
  canViewResult,
  hasAsset,
  isProcessing,
  isRefreshingStatus,
  isUploading,
  isRecording,
  onFileUpload,
  onDeleteMeeting,
  onProcess,
  onRefreshStatus,
  onRefreshHistory,
  onRenameMeeting,
  onStartRecording,
  onStopRecording,
  onOpenPlayback,
  selectedMeeting,
  onViewResult
}: MeetingActionPanelProps) {
  const canAct = Boolean(selectedMeeting);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isRetryAction = selectedMeeting?.retryAllowed === true;
  const isDraft = selectedMeeting?.status === "DRAFT";
  const isProcessingLocked = selectedMeeting?.status === "PROCESSING";
  const canSaveTitle =
    Boolean(selectedMeeting) && draftTitle.trim().length > 0 && draftTitle.trim() !== selectedMeeting?.title.trim();

  useEffect(() => {
    setIsRenaming(false);
    setDraftTitle(selectedMeeting?.title ?? "");
  }, [selectedMeeting?.id]);

  return (
    <section className="action-bar">
      {/* Left: meeting name + status */}
      <div className="action-bar__left">
        {isRenaming && selectedMeeting ? (
          <div className="action-bar__rename">
            <input
              autoFocus
              maxLength={240}
              value={draftTitle}
              disabled={isUploading || Boolean(isProcessing)}
              aria-label="Meeting title"
              onChange={(event) => setDraftTitle(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && canSaveTitle) {
                  onRenameMeeting(draftTitle);
                  setIsRenaming(false);
                }
                if (event.key === "Escape") {
                  setIsRenaming(false);
                  setDraftTitle(selectedMeeting.title);
                }
              }}
            />
            <IconOnlyButton icon={<Check size={16} />} disabled={!canSaveTitle || isUploading || Boolean(isProcessing)} label="Save name" onClick={() => { onRenameMeeting(draftTitle); setIsRenaming(false); }} />
            <IconOnlyButton icon={<X size={16} />} disabled={isUploading || Boolean(isProcessing)} label="Cancel rename" onClick={() => { setIsRenaming(false); setDraftTitle(selectedMeeting.title); }} />
          </div>
        ) : (
          <div className="action-bar__title-row">
            <h2 className="action-bar__title">{selectedMeeting.title}</h2>
            {selectedMeeting && (
              <IconOnlyButton icon={<Pencil size={16} />} disabled={isUploading || Boolean(isProcessing)} label="Rename meeting" onClick={() => { setDraftTitle(selectedMeeting.title); setIsRenaming(true); }} />
            )}
            {selectedMeeting && <StatusPill status={selectedMeeting.status} />}
          </div>
        )}
      </div>

      {/* Right: action buttons */}
      {selectedMeeting && (
        <div className="action-bar__right">
          {isDraft ? (
            <>
              <IconButton icon={<Upload size={16} />} label="Upload" disabled={!canUpload} variant="primary" onClick={() => fileInputRef.current?.click()} />
              <input ref={fileInputRef} type="file" hidden accept="audio/*,video/mp4,video/webm" onChange={(event) => { const file = event.target.files?.[0]; if (file) { onFileUpload(file); event.target.value = ""; } }} />
              <IconButton icon={isRecording ? <Pause size={16} /> : <Mic size={16} />} label={isRecording ? "Stop" : "Record"} disabled={!canUpload && !isRecording} onClick={isRecording ? onStopRecording : onStartRecording} variant={isRecording ? "danger" : "primary"} />
            </>
          ) : canViewResult ? (
            <IconButton icon={<Braces size={16} />} label="Result" disabled={!canAct} onClick={onViewResult} variant="primary" />
          ) : (
            <IconButton
              icon={isRetryAction ? <RotateCcw size={16} /> : <Play size={16} />}
              label={isProcessingLocked ? "Processing" : isRetryAction ? "Retry" : "Process"}
              disabled={!canAct || !canProcess || isProcessingLocked || Boolean(isProcessing)}
              title={isProcessingLocked ? "Meeting is currently being processed" : isRetryAction ? "Retry processing" : "Process meeting"}
              onClick={onProcess}
              variant="primary"
            />
          )}
          {hasAsset && (
            <IconButton icon={<Volume2 size={16} />} label="Playback" disabled={!canAct} onClick={onOpenPlayback} variant="primary" />
          )}
          <IconButton
            icon={<Trash2 size={16} />}
            label="Delete"
            disabled={!canAct || isProcessingLocked || isUploading}
            title={isProcessingLocked ? "Cannot delete while meeting is being processed" : "Delete"}
            onClick={() => setIsDeleteDialogOpen(true)}
            variant="danger"
          />
          <IconButton icon={<RefreshCw size={16} />} label="Refresh" disabled={!canAct || Boolean(isRefreshingStatus)} onClick={() => { onRefreshStatus(); onRefreshHistory(); }} variant="secondary" />
        </div>
      )}

      <ConfirmDialog
        isOpen={isDeleteDialogOpen}
        title="Delete meeting session"
        message={`Delete ${selectedMeeting?.title ?? "this meeting"}? This will delete its uploaded file, processing result, chunks, and chat history.`}
        confirmLabel="Delete session"
        onCancel={() => setIsDeleteDialogOpen(false)}
        onConfirm={() => { setIsDeleteDialogOpen(false); onDeleteMeeting(); }}
      />
    </section>
  );
}
