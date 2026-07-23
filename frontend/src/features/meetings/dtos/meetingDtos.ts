import type {
  ChatEvidenceState,
  ChatFeedbackCacheAction,
  ChatFeedbackResult,
  ChatFeedbackSelection,
  ChatFeedbackStatus,
  Meeting,
  MeetingAsset,
  MeetingFailureCode,
  MeetingChatAcceptedResult,
  MeetingChatCitation,
  MeetingChatHistory,
  MeetingChatMessage,
  MeetingChatMessageMetadata,
  MeetingChatResponse,
  MeetingIntelligenceResult,
} from "../types/meetingTypes";

type RawMeeting = {
  id?: unknown;
  title?: unknown;
  status?: unknown;
  failure_reason?: unknown;
  failure_code?: unknown;
  pending_chat_status?: unknown;
  created_at?: unknown;
  updated_at?: unknown;
  latest_asset?: unknown;
  retry_allowed?: unknown;
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



type RawChatCitation = {
  citation_id?: unknown;
  chunk_id?: unknown;
  source_type?: unknown;
  section_type?: unknown;
  json_pointer?: unknown;
  citation_ids?: unknown;
  segment_ids?: unknown;
  start_ms?: unknown;
  end_ms?: unknown;
  quote?: unknown;
  text?: unknown;
};

type RawChatMessage = {
  id?: unknown;
  role?: unknown;
  content?: unknown;
  retrieved_chunk_ids?: unknown;
  citations?: unknown;
  metadata?: unknown;
  feedback_rating?: unknown;
  feedback_revision?: unknown;
  feedbackRating?: unknown;
  feedbackRevision?: unknown;
  created_at?: unknown;
};

const PIPELINE_STAGES = new Set([
  "request_gate", "query_interpretation", "retrieval", "evidence_validation",
  "synthesis", "answer_verification", "output_policy", "persistence",
]);

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
    title: requireString(raw.title, "meeting.title"),
    status: requireString(raw.status, "meeting.status") as Meeting["status"],
    failureCode: parseMeetingFailureCode(raw.failure_code),
    failureReason: nullableString(raw.failure_reason, "meeting.failure_reason"),
    pendingChatStatus: raw.pending_chat_status != null ? String(raw.pending_chat_status) : null,
    createdAt: requireString(raw.created_at, "meeting.created_at"),
    updatedAt: requireString(raw.updated_at, "meeting.updated_at"),
    latestAsset: raw.latest_asset ? parseAsset(raw.latest_asset) : null,
    retryAllowed: Boolean(raw.retry_allowed)
  };
}

function parseMeetingFailureCode(value: unknown): MeetingFailureCode | null {
  if (value == null) {
    return null;
  }
  if (value === "NO_RECOGNIZABLE_SPEECH" || value === "PROCESSING_FAILED") {
    return value;
  }
  return "PROCESSING_FAILED";
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



export function buildChatPayload(question: string) {
  return {
    question: question.trim(),
    language: typeof navigator === "undefined" ? undefined : navigator.language,
  };
}

export function buildChatFeedbackPayload(rating: ChatFeedbackSelection, expectedRevision?: number) {
  return {
    rating,
    ...(typeof expectedRevision === "number" && expectedRevision >= 0
      ? { expected_revision: expectedRevision }
      : {}),
  };
}

export function buildMeetingTitlePayload(title: string) {
  return {
    title: title.trim()
  };
}

export function parseMeetingChatResponse(raw: unknown): MeetingChatResponse {
  const response = raw as {
    answer?: unknown;
    evidence_state?: unknown;
    citations?: unknown;
    message?: unknown;
  };
  return {
    answer: requireString(response.answer, "chat.answer"),
    evidenceState: requireString(response.evidence_state, "chat.evidence_state") as MeetingChatResponse["evidenceState"],
    citations: mapCitations(response.citations),
    message: parseMeetingChatMessage(response.message)
  };
}

export function parseMeetingChatHistory(raw: unknown): MeetingChatHistory {
  const history = raw as {
    meeting_id?: unknown;
    title?: unknown;
    messages?: unknown;
  };
  if (!Array.isArray(history.messages)) {
    throw new Error("Invalid chat history.");
  }
  return {
    meetingId: requireString(history.meeting_id, "chat_history.meeting_id"),
    title: requireString(history.title, "chat_history.title"),
    messages: history.messages.map(parseMeetingChatMessage)
  };
}

export function parseMeetingChatAccepted(raw: unknown): MeetingChatAcceptedResult {
  const response = raw as { status?: unknown; message?: unknown; turn_id?: unknown };
  const status = requireString(response.status, "chat.status");
  if (status !== "processing" && status !== "clarification_needed") {
    throw new Error("Invalid chat.status.");
  }
  return {
    status,
    message: requireString(response.message, "chat.message"),
    turnId: requireString(response.turn_id, "chat.turn_id"),
  };
}

export function parseChatFeedbackResponse(raw: unknown): ChatFeedbackResult {
  const response = raw as {
    message_id?: unknown;
    rating?: unknown;
    revision?: unknown;
    feedback_revision?: unknown;
    status?: unknown;
    memory_status?: unknown;
    cache_action?: unknown;
  };
  const rating = parseFeedbackSelection(response.rating);
  const revision = nonNegativeInteger(response.revision ?? response.feedback_revision, 0);
  return {
    messageId: requireString(response.message_id, "chat_feedback.message_id"),
    rating,
    revision,
    status: parseFeedbackStatus(response.memory_status ?? response.status),
    cacheAction: parseFeedbackCacheAction(response.cache_action),
  };
}

export function parseMeetingChatMessage(value: unknown): MeetingChatMessage {
  const raw = value as RawChatMessage;
  const role = requireString(raw.role, "chat_message.role");
  if (role !== "user" && role !== "assistant") {
    throw new Error("Invalid chat_message.role.");
  }
  const metadata = parsePublicChatMetadata(raw.metadata);
  const feedbackRating = parseFeedbackRating(raw.feedback_rating ?? raw.feedbackRating);
  const feedbackRevision = nonNegativeInteger(raw.feedback_revision ?? raw.feedbackRevision, 0);
  
  return {
    id: requireString(raw.id, "chat_message.id"),
    role,
    content: requireString(raw.content, "chat_message.content"),
    retrievedChunkIds: stringList(raw.retrieved_chunk_ids, "chat_message.retrieved_chunk_ids"),
    citations: mapCitations(raw.citations),
    metadata,
    feedbackRating,
    feedbackRevision,
    createdAt: requireString(raw.created_at, "chat_message.created_at"),
  };
}

function parsePublicChatMetadata(raw: unknown): MeetingChatMessageMetadata {
  if (!isRecord(raw)) {
    return {};
  }
  const evidenceState = parseEvidenceState(raw.evidenceState ?? raw.evidence_state);
  const metadata: MeetingChatMessageMetadata = {};
  if (evidenceState) metadata.evidenceState = evidenceState;
  const origin = raw.answerOriginKind ?? raw.answer_origin_kind;
  if (origin === "llm_synthesis" || origin === "control") metadata.answerOriginKind = origin;
  if (typeof raw.provider === "string") metadata.provider = raw.provider;
  if (typeof raw.model === "string") metadata.model = raw.model;
  assignBoolean(metadata, "feedbackEligible", raw.feedbackEligible ?? raw.feedback_eligible);
  assignBoolean(metadata, "local", raw.local);
  assignBoolean(metadata, "pending", raw.pending);
  assignBoolean(metadata, "streaming", raw.streaming);
  const trace = parsePipelineTrace(raw.pipelineTrace ?? raw.pipeline_trace);
  if (trace) metadata.pipelineTrace = trace;
  const explicitClarification = raw.clarificationNeeded ?? raw.clarification_needed;
  if (typeof explicitClarification === "boolean") {
    metadata.clarificationNeeded = explicitClarification;
  } else if (evidenceState === "clarification_needed") {
    metadata.clarificationNeeded = true;
  }
  return metadata;
}

function parsePipelineTrace(value: unknown): MeetingChatMessageMetadata["pipelineTrace"] | undefined {
  if (!isRecord(value) || value.version !== 1 || value.contract !== "simple-rag.v1" || !Array.isArray(value.stages)) return undefined;
  const stages = value.stages.slice(0, 16).flatMap((item) => {
    if (!isRecord(item) || typeof item.stage !== "string" || !PIPELINE_STAGES.has(item.stage) || typeof item.status !== "string") return [];
    if (!isJsonValue(item.details)) return [];
    return [{
      stage: item.stage as NonNullable<MeetingChatMessageMetadata["pipelineTrace"]>["stages"][number]["stage"],
      status: item.status,
      durationMs: typeof item.durationMs === "number" && item.durationMs >= 0 ? item.durationMs : 0,
      provider: typeof item.provider === "string" ? item.provider : null,
      model: typeof item.model === "string" ? item.model : null,
      details: item.details,
    }];
  });
  return { version: 1, contract: "simple-rag.v1", stages };
}

function isJsonValue(value: unknown): value is import("../types/meetingTypes").JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) return value.every(isJsonValue);
  if (isRecord(value)) return Object.values(value).every(isJsonValue);
  return false;
}

function assignNonNegativeNumber<T extends object, K extends keyof T>(target: T, key: K, value: unknown) {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    target[key] = value as T[K];
  }
}

function parseEvidenceState(value: unknown): ChatEvidenceState | undefined {
  return value === "grounded"
    || value === "partial"
    || value === "not_enough_evidence"
    || value === "direct"
    || value === "blocked"
    || value === "error"
    || value === "clarification_needed"
    ? value
    : undefined;
}

function parseFeedbackRating(value: unknown): "up" | "down" | null {
  return value === "up" || value === "down" ? value : null;
}

function parseFeedbackSelection(value: unknown): ChatFeedbackSelection {
  if (value === "up" || value === "down" || value === "neutral") {
    return value;
  }
  throw new Error("Invalid chat_feedback.rating.");
}

function parseFeedbackStatus(value: unknown): ChatFeedbackStatus {
  return value === "queued"
    || value === "pending"
    || value === "active"
    || value === "inactive"
    || value === "removed"
    || value === "ineligible"
    || value === "source_retained"
    || value === "failed"
    || value === "unchanged"
    || value === "disabled"
    ? value
    : "unknown";
}

function parseFeedbackCacheAction(value: unknown): ChatFeedbackCacheAction {
  return value === "none"
    || value === "invalidated"
    || value === "evicted"
    || value === "promoted"
    || value === "semantic_mapping_quarantined"
    || value === "not_found"
    || value === "skipped"
    || value === "disabled"
    ? value
    : "unknown";
}

function nonNegativeInteger(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : fallback;
}

function assignBoolean<K extends keyof MeetingChatMessageMetadata>(
  target: MeetingChatMessageMetadata,
  key: K,
  value: unknown,
) {
  if (typeof value === "boolean") {
    target[key] = value as MeetingChatMessageMetadata[K];
  }
}

function mapCitations(raw: unknown): MeetingChatCitation[] {
  if (!Array.isArray(raw)) {
    throw new Error("Invalid chat citations.");
  }
  return raw.map((item) => {
    const citation = item as RawChatCitation;
    const legacyCitationIds = citation.citation_ids;
    const citationId = citation.citation_id ?? (
      Array.isArray(legacyCitationIds) && typeof legacyCitationIds[0] === "string"
        ? legacyCitationIds[0]
        : null
    );
    return {
      citationId: requireString(citationId, "chat_citation.citation_id"),
      chunkId: requireString(citation.chunk_id, "chat_citation.chunk_id"),
      sourceType: requireString(citation.source_type, "chat_citation.source_type"),
      sectionType: requireString(citation.section_type, "chat_citation.section_type"),
      jsonPointer: requireString(citation.json_pointer, "chat_citation.json_pointer"),
      segmentIds: stringList(citation.segment_ids, "chat_citation.segment_ids"),
      startMs: nullableNumber(citation.start_ms, "chat_citation.start_ms"),
      endMs: nullableNumber(citation.end_ms, "chat_citation.end_ms"),
      quote: requireString(citation.quote ?? citation.text, "chat_citation.quote")
    };
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseMeetingIntelligenceResult(raw: unknown): MeetingIntelligenceResult {
  if (!isRecord(raw)) {
    throw new Error("Invalid meeting intelligence result.");
  }
  if (raw.schemaVersion === "meeting-intelligence-result.v2") {
    const knowledge = raw.knowledge;
    const evidence = raw.evidence;
    if (!isRecord(knowledge) || !Array.isArray(knowledge.records)) {
      throw new Error("Invalid v2 knowledge records.");
    }
    if (!isRecord(evidence) || !Array.isArray(evidence.items)) {
      throw new Error("Invalid v2 evidence items.");
    }
    const evidenceIds = new Set(
      evidence.items.filter(isRecord).map((item) => item.id).filter((id): id is string => typeof id === "string")
    );
    for (const record of knowledge.records) {
      if (!isRecord(record) || typeof record.id !== "string" || typeof record.type !== "string" || typeof record.subtype !== "string") {
        throw new Error("Invalid v2 knowledge record envelope.");
      }
      if (!Array.isArray(record.evidenceRefs) || record.evidenceRefs.some((id) => typeof id !== "string" || !evidenceIds.has(id))) {
        throw new Error(`Invalid evidence references for record ${record.id}.`);
      }
    }
  }
  return raw;
}
