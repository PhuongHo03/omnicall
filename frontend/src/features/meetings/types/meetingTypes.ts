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
  citationId: string;
  chunkId: string;
  sourceType: string;
  sectionType: string;
  jsonPointer: string;
  segmentIds: string[];
  startMs: number | null;
  endMs: number | null;
  quote: string;
};

export type PlaybackSeekRequest = {
  startMs: number | null;
  endMs: number | null;
  segmentIds: string[];
};

export type MeetingChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  retrievedChunkIds: string[];
  citations: MeetingChatCitation[];
  metadata: Record<string, unknown>;
  agentMetadata?: {
    iterations?: number;
    replans?: number;
    toolCalls?: string[];
    agentThoughts?: string[];
    intent?: string;
    sections?: string[];
    missingFields?: string[];
    evidenceCount?: number;
  };
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
