import { Download, FileAudio, FileVideo, FileText } from "lucide-react";

import { IconOnlyButton } from "../../../shared/components/IconOnlyButton";
import type { MeetingAsset, MediaKind } from "../types/meetingTypes";
import { formatFileSize } from "../utils/meetingFormatters";

type AssetMetadataBarProps = {
  asset: MeetingAsset;
  mediaKind: MediaKind;
  duration: number;
  onDownload: () => void;
};

const KIND_ICON: Record<MediaKind, typeof FileAudio> = {
  audio: FileAudio,
  video: FileVideo,
};

const KIND_LABEL: Record<MediaKind, string> = {
  audio: "Audio",
  video: "Video",
};

function getContentTypeBadge(contentType: string): string {
  const map: Record<string, string> = {
    "audio/mpeg": "MP3",
    "audio/wav": "WAV",
    "audio/webm": "WEBM",
    "audio/ogg": "OGG",
    "audio/mp4": "M4A",
    "video/mp4": "MP4",
    "video/webm": "WEBM",
  };
  if (map[contentType]) return map[contentType];
  const parts = contentType.split("/");
  return (parts[1] ?? contentType).toUpperCase();
}

export function AssetMetadataBar({ asset, mediaKind, duration, onDownload }: AssetMetadataBarProps) {
  const Icon = KIND_ICON[mediaKind] ?? FileText;
  const durationLabel = formatTimeShort(duration);
  const badge = getContentTypeBadge(asset.contentType);

  return (
    <div className="apb-metadata">
      <div className="apb-metadata__icon">
        <Icon size={16} />
      </div>
      <div className="apb-metadata__info">
        <span className="apb-metadata__name" title={asset.fileName}>{asset.fileName}</span>
        <span className="apb-metadata__details">
          {badge} · {formatFileSize(asset.sizeBytes)}
          {durationLabel ? ` · ${durationLabel}` : ""}
          {` · ${KIND_LABEL[mediaKind]}`}
        </span>
      </div>
      <IconOnlyButton
        icon={<Download size={16} />}
        label="Download file"
        onClick={onDownload}
      />
    </div>
  );
}

function formatTimeShort(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  const totalSeconds = Math.floor(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}
