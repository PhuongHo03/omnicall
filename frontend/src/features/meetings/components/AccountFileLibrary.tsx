import { FileAudio, Play, RefreshCw, Trash2, Upload } from "lucide-react";

import { IconButton } from "../../../components/IconButton";
import type { AccountFile } from "../types/meetingTypes";

type AccountFileLibraryProps = {
  disabled: boolean;
  files: AccountFile[];
  playbackUrl: string | null;
  selectedFileId: string | null;
  onDelete: (fileId: string) => void;
  onPlay: (fileId: string) => void;
  onRefresh: () => void;
  onUpload: (file: File) => void;
};

export function AccountFileLibrary({
  disabled,
  files,
  onDelete,
  onPlay,
  onRefresh,
  onUpload,
  playbackUrl,
  selectedFileId
}: AccountFileLibraryProps) {
  const selectedFile = files.find((file) => file.id === selectedFileId) ?? null;

  return (
    <section className="file-library-panel">
      <div className="panel-heading panel-heading--with-action">
        <h2>Files</h2>
        <IconButton icon={<RefreshCw size={15} />} label="Refresh" disabled={disabled} onClick={onRefresh} />
      </div>
      <label className="library-upload">
        <Upload size={16} />
        <span>Store file</span>
        <input
          type="file"
          accept="audio/*,video/mp4,video/webm,.txt,.md,.vtt,.srt,text/plain,text/markdown,text/vtt,application/x-subrip"
          disabled={disabled}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              onUpload(file);
              event.target.value = "";
            }
          }}
        />
      </label>

      <div className="file-library-list">
        {files.length === 0 ? (
          <div className="empty-panel">No uploaded files.</div>
        ) : (
          files.map((file) => (
            <article className="file-card" key={file.id}>
              <div className="file-card__title">
                <FileAudio size={15} />
                <span>{file.fileName}</span>
              </div>
              <span>{formatBytes(file.sizeBytes)}</span>
              <span>{file.linkedToMeeting ? "Linked to meeting" : "Unlinked"}</span>
              <div className="file-card__actions">
                <button type="button" disabled={disabled} onClick={() => onPlay(file.id)} title="Play or preview">
                  <Play size={14} />
                </button>
                <button
                  type="button"
                  disabled={disabled || file.linkedToMeeting}
                  onClick={() => onDelete(file.id)}
                  title={file.linkedToMeeting ? "Delete the meeting session first" : "Delete file"}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </article>
          ))
        )}
      </div>

      {playbackUrl && selectedFile ? (
        <div className="library-player">
          <span>{selectedFile.fileName}</span>
          {selectedFile.contentType.startsWith("audio/") ? (
            <audio src={playbackUrl} controls preload="metadata" />
          ) : (
            <a href={playbackUrl} target="_blank" rel="noreferrer">
              Open file
            </a>
          )}
        </div>
      ) : null}
    </section>
  );
}

function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
