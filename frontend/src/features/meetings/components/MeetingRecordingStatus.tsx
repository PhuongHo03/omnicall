import { Download, RotateCcw, Trash2 } from "lucide-react";

import { EmptyState } from "../../../shared/components/EmptyState";
import { IconButton } from "../../../shared/components/IconButton";
import type { RecordingSession } from "../types/meetingTypes";
import { MeetingProgressBar } from "./MeetingProgressBar";

type MeetingRecordingStatusProps = {
  session: RecordingSession;
  uploadProgress: number | null;
  canRetry: boolean;
  onDiscard: () => void;
  onDownload: () => void;
  onRetry: () => void;
};

export function MeetingRecordingStatus({ session, uploadProgress, canRetry, onDiscard, onDownload, onRetry }: MeetingRecordingStatusProps) {
  if (session.phase === "failed" || session.phase === "recoverable") {
    return (
      <EmptyState
        message={session.isPartial ? "Đã khôi phục một phần bản ghi" : "Bản ghi đang chờ tải lại"}
        description={session.error ?? "Bản ghi được lưu an toàn trong trình duyệt này."}
      >
        <div className="action-bar__right">
          <IconButton icon={<RotateCcw size={16} />} label="Retry" disabled={!canRetry} title={canRetry ? "Retry recording upload" : "The original meeting is no longer uploadable"} variant="primary" onClick={onRetry} />
          <IconButton icon={<Download size={16} />} label="Download" title="Download recording" variant="secondary" onClick={onDownload} />
          <IconButton icon={<Trash2 size={16} />} label="Discard" title="Discard recording" variant="danger" onClick={onDiscard} />
        </div>
        {session.storageWarning && <p role="alert">{session.storageWarning}</p>}
      </EmptyState>
    );
  }

  const message = {
    requesting_permission: "Đang xin quyền microphone…",
    recording: "Đang ghi âm…",
    finalizing: "Đang hoàn tất bản ghi…",
    uploading: "Đang tải bản ghi lên…",
  }[session.phase] ?? "Đang chuẩn bị bản ghi…";

  return (
    <EmptyState message={message} description={session.storageWarning ?? undefined}>
      {session.phase === "uploading" && (
        <MeetingProgressBar label="Recording upload progress" value={uploadProgress ?? 0} />
      )}
    </EmptyState>
  );
}
