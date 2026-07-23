export type MeetingStatus = "DRAFT" | "UPLOADED" | "QUEUED" | "PROCESSING" | "READY" | "FAILED";
export type MeetingFailureCode = "NO_RECOGNIZABLE_SPEECH" | "PROCESSING_FAILED";

export type Meeting = {
  id: string;
  title: string;
  status: MeetingStatus;
  failureCode: MeetingFailureCode | null;
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

export type RecordingPhase =
  | "idle"
  | "requesting_permission"
  | "recording"
  | "finalizing"
  | "uploading"
  | "failed"
  | "recoverable";

export type StoredRecordingSession = {
  id: string;
  ownerId: string;
  meetingId: string;
  phase: Exclude<RecordingPhase, "idle">;
  mimeType: string;
  fileName: string;
  startedAt: number;
  updatedAt: number;
  durationMs: number;
  chunkCount: number;
  uploadProgress: number | null;
  isPartial: boolean;
  error: string | null;
};

export type StoredRecordingChunk = {
  sessionId: string;
  sequence: number;
  data: ArrayBuffer;
  createdAt: number;
};

export type RecordingSession = StoredRecordingSession & {
  file: File | null;
  storageWarning: string | null;
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

export type ChatEvidenceState =
  | "grounded"
  | "partial"
  | "not_enough_evidence"
  | "direct"
  | "blocked"
  | "error"
  | "clarification_needed";

export type ChatFeedbackRating = "up" | "down";
export type ChatFeedbackSelection = ChatFeedbackRating | "neutral";

export type ChatFeedbackStatus =
  | "queued"
  | "pending"
  | "active"
  | "inactive"
  | "removed"
  | "ineligible"
  | "disabled"
  | "source_retained"
  | "failed"
  | "unchanged"
  | "unknown";

export type ChatFeedbackCacheAction =
  | "none"
  | "invalidated"
  | "evicted"
  | "promoted"
  | "semantic_mapping_quarantined"
  | "not_found"
  | "skipped"
  | "disabled"
  | "unknown";

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type PipelineTraceStage = {
  stage: "request_gate" | "query_interpretation" | "retrieval" | "evidence_validation" | "synthesis" | "answer_verification" | "output_policy" | "persistence";
  status: string;
  durationMs: number;
  provider: string | null;
  model: string | null;
  details: JsonValue;
};

export type PipelineTrace = {
  version: 1;
  contract: "simple-rag.v1";
  stages: PipelineTraceStage[];
};

export type MeetingChatMessageMetadata = {
  evidenceState?: ChatEvidenceState;
  answerOriginKind?: "llm_synthesis" | "control";
  provider?: string;
  model?: string;
  feedbackEligible?: boolean;
  clarificationNeeded?: boolean;
  pipelineTrace?: PipelineTrace;
  local?: boolean;
  pending?: boolean;
  streaming?: boolean;
};

export type MeetingChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  retrievedChunkIds: string[];
  citations: MeetingChatCitation[];
  metadata: MeetingChatMessageMetadata;
  feedbackRating: ChatFeedbackRating | null;
  feedbackRevision: number;
  feedbackStatus?: ChatFeedbackStatus;
  feedbackCacheAction?: ChatFeedbackCacheAction;
  createdAt: string;
};

export type ChatFeedbackResult = {
  messageId: string;
  rating: ChatFeedbackSelection;
  revision: number;
  status: ChatFeedbackStatus;
  cacheAction: ChatFeedbackCacheAction;
};

export type MeetingChatAcceptedResult = {
  status: "processing" | "clarification_needed";
  message: string;
  turnId: string;
};

export type ChatStreamEvent =
  | { type: "status"; turnId: string; stage: string; message: string }
  | { type: "token"; token: string }
  | { type: "done"; turnId: string; answer: string; assistantMessage?: MeetingChatMessage }
  | { type: "clarification"; turnId: string; message: string; assistantMessage?: MeetingChatMessage }
  | { type: "clarification_needed"; turnId: string; message: string; assistantMessage?: MeetingChatMessage }
  | { type: "blocked"; turnId: string; message: string; assistantMessage?: MeetingChatMessage }
  | { type: "error"; turnId: string; message: string }
  | { type: "connected"; status: string };

export type MeetingChatResponse = {
  answer: string;
  evidenceState: ChatEvidenceState;
  citations: MeetingChatCitation[];
  message: MeetingChatMessage;
};

export type MeetingChatHistory = {
  meetingId: string;
  title: string;
  messages: MeetingChatMessage[];
};

export type MeetingIntelligenceResult = Record<string, unknown>;

export type KnowledgeRecord = {
  id: string;
  type: string;
  subtype: string;
  data: Record<string, unknown>;
  scope: string;
  evidenceRefs: string[];
  sourceRefs: string[];
  derivedFrom: string[];
  confidence: number;
  status: string;
};

// ── Asset playback types ──

export type TranscriptEntry = {
  id: string;
  speaker: string;
  startMs: number;
  endMs: number;
  text: string;
};

export type MediaKind = "audio" | "video";
