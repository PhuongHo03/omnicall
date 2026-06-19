export type MeetingStatus = "DRAFT" | "UPLOADED" | "QUEUED" | "PROCESSING" | "READY" | "FAILED";

export type ProcessingJobStatus = "PENDING" | "RUNNING" | "RETRYING" | "SUCCEEDED" | "FAILED" | "CANCELLED";

export type Meeting = {
  id: string;
  title: string;
  language: string | null;
  status: MeetingStatus;
  failureReason: string | null;
  createdAt: string;
  updatedAt: string;
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

export type ProcessingJob = {
  id: string;
  meetingId: string;
  status: ProcessingJobStatus;
  safeFailureReason: string | null;
  retryAllowed: boolean;
  createdAt: string;
  updatedAt: string;
};

export type ProcessingStatus = {
  meeting: Meeting;
  latestJob: ProcessingJob | null;
  latestAsset: MeetingAsset | null;
};

export type MeetingDraft = {
  title: string;
  language: string;
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

export type AccountFile = {
  id: string;
  ownerUserId: string;
  meetingId: string | null;
  fileName: string;
  contentType: string;
  sizeBytes: number;
  linkedToMeeting: boolean;
  createdAt: string;
};
