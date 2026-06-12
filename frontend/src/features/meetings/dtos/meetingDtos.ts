import type {
  Meeting,
  MeetingAsset,
  MeetingChatCitation,
  MeetingChatHistory,
  MeetingChatMessage,
  MeetingChatResponse,
  ProcessingJob,
  ProcessingStatus
} from "../types/meetingTypes";

type RawMeeting = {
  id?: unknown;
  workspace_id?: unknown;
  title?: unknown;
  language?: unknown;
  status?: unknown;
  failure_reason?: unknown;
  created_at?: unknown;
  updated_at?: unknown;
};

type RawAsset = {
  id?: unknown;
  meeting_id?: unknown;
  object_key?: unknown;
  file_name?: unknown;
  content_type?: unknown;
  size_bytes?: unknown;
  created_at?: unknown;
};

type RawJob = {
  id?: unknown;
  meeting_id?: unknown;
  status?: unknown;
  safe_failure_reason?: unknown;
  retry_allowed?: unknown;
  created_at?: unknown;
  updated_at?: unknown;
};

type RawChatCitation = {
  chunk_id?: unknown;
  source_type?: unknown;
  section_type?: unknown;
  json_pointer?: unknown;
  citation_ids?: unknown;
  segment_ids?: unknown;
  start_ms?: unknown;
  end_ms?: unknown;
  text?: unknown;
};

type RawChatMessage = {
  id?: unknown;
  session_id?: unknown;
  role?: unknown;
  content?: unknown;
  retrieved_chunk_ids?: unknown;
  citations?: unknown;
  metadata?: unknown;
  created_at?: unknown;
};

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string") {
    throw new Error(`Invalid ${field}.`);
  }
  return value;
}

function nullableString(value: unknown, field: string): string | null {
  if (value === null) {
    return null;
  }
  return requireString(value, field);
}

function nullableNumber(value: unknown, field: string): number | null {
  if (value === null) {
    return null;
  }
  if (typeof value !== "number") {
    throw new Error(`Invalid ${field}.`);
  }
  return value;
}

function stringList(value: unknown, field: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error(`Invalid ${field}.`);
  }
  return value.map((item) => requireString(item, field));
}

function mapMeeting(raw: RawMeeting): Meeting {
  return {
    id: requireString(raw.id, "meeting.id"),
    workspaceId: requireString(raw.workspace_id, "meeting.workspace_id"),
    title: requireString(raw.title, "meeting.title"),
    language: raw.language === null ? null : requireString(raw.language, "meeting.language"),
    status: requireString(raw.status, "meeting.status") as Meeting["status"],
    failureReason: nullableString(raw.failure_reason, "meeting.failure_reason"),
    createdAt: requireString(raw.created_at, "meeting.created_at"),
    updatedAt: requireString(raw.updated_at, "meeting.updated_at")
  };
}

function mapJob(raw: RawJob): ProcessingJob {
  return {
    id: requireString(raw.id, "job.id"),
    meetingId: requireString(raw.meeting_id, "job.meeting_id"),
    status: requireString(raw.status, "job.status") as ProcessingJob["status"],
    safeFailureReason: nullableString(raw.safe_failure_reason, "job.safe_failure_reason"),
    retryAllowed: Boolean(raw.retry_allowed),
    createdAt: requireString(raw.created_at, "job.created_at"),
    updatedAt: requireString(raw.updated_at, "job.updated_at")
  };
}

export function parseMeeting(raw: unknown): Meeting {
  return mapMeeting(raw as RawMeeting);
}

export function parseMeetingList(raw: unknown): Meeting[] {
  const items = (raw as { items?: unknown }).items;
  if (!Array.isArray(items)) {
    throw new Error("Invalid meeting list.");
  }
  return items.map((item) => mapMeeting(item as RawMeeting));
}

export function parseAsset(raw: unknown): MeetingAsset {
  const asset = raw as RawAsset;
  const sizeBytes = asset.size_bytes;
  if (typeof sizeBytes !== "number") {
    throw new Error("Invalid asset.size_bytes.");
  }
  return {
    id: requireString(asset.id, "asset.id"),
    meetingId: requireString(asset.meeting_id, "asset.meeting_id"),
    objectKey: requireString(asset.object_key, "asset.object_key"),
    fileName: requireString(asset.file_name, "asset.file_name"),
    contentType: requireString(asset.content_type, "asset.content_type"),
    sizeBytes,
    createdAt: requireString(asset.created_at, "asset.created_at")
  };
}

export function parseProcessingJob(raw: unknown): ProcessingJob {
  return mapJob(raw as RawJob);
}

export function parseProcessingStatus(raw: unknown): ProcessingStatus {
  const status = raw as { meeting?: unknown; latest_job?: unknown };
  return {
    meeting: mapMeeting(status.meeting as RawMeeting),
    latestJob: status.latest_job ? mapJob(status.latest_job as RawJob) : null
  };
}

export function buildMeetingPayload(title: string, language: string) {
  return {
    title: title.trim(),
    language: language.trim() || null
  };
}

export function buildChatPayload(question: string, sessionId: string | null, language: string | null) {
  return {
    question: question.trim(),
    session_id: sessionId,
    language
  };
}

export function parseMeetingChatResponse(raw: unknown): MeetingChatResponse {
  const response = raw as {
    session_id?: unknown;
    answer?: unknown;
    evidence_state?: unknown;
    citations?: unknown;
    message?: unknown;
  };
  return {
    sessionId: requireString(response.session_id, "chat.session_id"),
    answer: requireString(response.answer, "chat.answer"),
    evidenceState: requireString(response.evidence_state, "chat.evidence_state") as MeetingChatResponse["evidenceState"],
    citations: mapCitations(response.citations),
    message: mapChatMessage(response.message as RawChatMessage)
  };
}

export function parseMeetingChatHistory(raw: unknown): MeetingChatHistory {
  const history = raw as {
    session_id?: unknown;
    meeting_id?: unknown;
    title?: unknown;
    messages?: unknown;
  };
  if (!Array.isArray(history.messages)) {
    throw new Error("Invalid chat history.");
  }
  return {
    sessionId: requireString(history.session_id, "chat_history.session_id"),
    meetingId: requireString(history.meeting_id, "chat_history.meeting_id"),
    title: requireString(history.title, "chat_history.title"),
    messages: history.messages.map((message) => mapChatMessage(message as RawChatMessage))
  };
}

function mapChatMessage(raw: RawChatMessage): MeetingChatMessage {
  const role = requireString(raw.role, "chat_message.role");
  if (role !== "user" && role !== "assistant") {
    throw new Error("Invalid chat_message.role.");
  }
  return {
    id: requireString(raw.id, "chat_message.id"),
    sessionId: requireString(raw.session_id, "chat_message.session_id"),
    role,
    content: requireString(raw.content, "chat_message.content"),
    retrievedChunkIds: stringList(raw.retrieved_chunk_ids, "chat_message.retrieved_chunk_ids"),
    citations: mapCitations(raw.citations),
    metadata: isRecord(raw.metadata) ? raw.metadata : {},
    createdAt: requireString(raw.created_at, "chat_message.created_at")
  };
}

function mapCitations(raw: unknown): MeetingChatCitation[] {
  if (!Array.isArray(raw)) {
    throw new Error("Invalid chat citations.");
  }
  return raw.map((item) => {
    const citation = item as RawChatCitation;
    return {
      chunkId: requireString(citation.chunk_id, "chat_citation.chunk_id"),
      sourceType: requireString(citation.source_type, "chat_citation.source_type"),
      sectionType: requireString(citation.section_type, "chat_citation.section_type"),
      jsonPointer: requireString(citation.json_pointer, "chat_citation.json_pointer"),
      citationIds: stringList(citation.citation_ids, "chat_citation.citation_ids"),
      segmentIds: stringList(citation.segment_ids, "chat_citation.segment_ids"),
      startMs: nullableNumber(citation.start_ms, "chat_citation.start_ms"),
      endMs: nullableNumber(citation.end_ms, "chat_citation.end_ms"),
      text: requireString(citation.text, "chat_citation.text")
    };
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
