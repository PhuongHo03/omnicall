export type MeetingStatus = "DRAFT" | "UPLOADED" | "QUEUED" | "PROCESSING" | "READY" | "FAILED";

export type Meeting = {
  id: string;
  title: string;
  status: MeetingStatus;
  failureReason: string | null;
  pendingChatStatus: string | null;
  createdAt: string;
  updatedAt: string;
  latestAsset: MeetingAsset | null;
  retryAllowed: boolean;
};

export type MeetingAsset = {
  id: string;
  meetingId: string;
  objectKey: string;
  fileName: string;
  contentType: string;
  sizeBytes: number;
  createdAt: string;
};

export type MeetingChatCitation = {
  chunkId: string;
  sourceType: string;
  sectionType: string;
  jsonPointer: string;
  citationIds: string[];
  segmentIds: string[];
  startMs: number | null;
  endMs: number | null;
  text: string;
};

export type MeetingChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  retrievedChunkIds: string[];
  citations: MeetingChatCitation[];
  metadata: Record<string, unknown>;
  createdAt: string;
};

export type MeetingChatResponse = {
  answer: string;
  evidenceState: "grounded" | "partial" | "not_enough_evidence";
  citations: MeetingChatCitation[];
  message: MeetingChatMessage;
};

export type MeetingChatHistory = {
  meetingId: string;
  title: string;
  messages: MeetingChatMessage[];
};

export type MeetingIntelligenceResult = Record<string, unknown>;

// ── Asset playback types ──

export type TranscriptEntry = {
  id: string;
  speaker: string;
  startMs: number;
  endMs: number;
  text: string;
};

export type MediaKind = "audio" | "video";

export function resolveMediaKind(asset: MeetingAsset): MediaKind {
  if (asset.contentType.startsWith("video/")) return "video";
  return "audio";
}

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const totalSeconds = Math.floor(seconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

export function formatFileSize(bytes: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}
