import type {
  Meeting,
  MeetingAsset,
  MeetingChatCitation,
  MeetingChatHistory,
  MeetingChatMessage,
  MeetingChatResponse,
  MeetingIntelligenceResult,
} from "../types/meetingTypes";

type RawMeeting = {
  id?: unknown;
  title?: unknown;
  status?: unknown;
  failure_reason?: unknown;
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
    title: requireString(raw.title, "meeting.title"),
    status: requireString(raw.status, "meeting.status") as Meeting["status"],
    failureReason: nullableString(raw.failure_reason, "meeting.failure_reason"),
    pendingChatStatus: raw.pending_chat_status != null ? String(raw.pending_chat_status) : null,
    createdAt: requireString(raw.created_at, "meeting.created_at"),
    updatedAt: requireString(raw.updated_at, "meeting.updated_at"),
    latestAsset: raw.latest_asset ? parseAsset(raw.latest_asset) : null,
    retryAllowed: Boolean(raw.retry_allowed)
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



export function buildChatPayload(question: string) {
  return {
    question: question.trim()
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
    message: mapChatMessage(response.message as RawChatMessage)
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
    messages: history.messages.map((message) => mapChatMessage(message as RawChatMessage))
  };
}

function mapChatMessage(raw: RawChatMessage): MeetingChatMessage {
  const role = requireString(raw.role, "chat_message.role");
  if (role !== "user" && role !== "assistant") {
    throw new Error("Invalid chat_message.role.");
  }
  const metadata = isRecord(raw.metadata) ? raw.metadata : {};
  
  // Map agentMetadata from backend agentToolCalls
  const agentToolCalls = Array.isArray((metadata as Record<string, unknown>).agentToolCalls) 
    ? (metadata as Record<string, unknown>).agentToolCalls as Array<{tool: string}>
    : undefined;
  const agentReplans = typeof metadata.agentReplans === "number" ? metadata.agentReplans : undefined;
  const agentIterations = typeof metadata.agentIterations === "number" ? metadata.agentIterations : undefined;
  const queryPlan = isRecord(metadata.agentQueryPlan) ? metadata.agentQueryPlan : {};
  const planSections = Array.isArray(queryPlan.sections) ? queryPlan.sections.filter((item): item is string => typeof item === "string") : undefined;
  const planRecordTypes = Array.isArray(queryPlan.recordTypes) ? queryPlan.recordTypes.filter((item): item is string => typeof item === "string") : undefined;
  const planRecordSubtypes = Array.isArray(queryPlan.recordSubtypes) ? queryPlan.recordSubtypes.filter((item): item is string => typeof item === "string") : undefined;
  const planRelationTypes = Array.isArray(queryPlan.relationTypes) ? queryPlan.relationTypes.filter((item): item is string => typeof item === "string") : undefined;
  const planAnswerShape = typeof queryPlan.answerShape === "string" ? queryPlan.answerShape : undefined;
  const agentMetadata = agentToolCalls || agentReplans !== undefined || agentIterations !== undefined || planSections || planRecordTypes || planRecordSubtypes || planRelationTypes || planAnswerShape
    ? {
        iterations: agentIterations,
        replans: agentReplans,
        toolCalls: agentToolCalls?.map(tc => tc.tool),
        intent: typeof queryPlan.intent === "string" ? queryPlan.intent : undefined,
        sections: planSections,
        recordTypes: planRecordTypes,
        recordSubtypes: planRecordSubtypes,
        relationTypes: planRelationTypes,
        answerShape: planAnswerShape,
      }
    : undefined;
  
  return {
    id: requireString(raw.id, "chat_message.id"),
    role,
    content: requireString(raw.content, "chat_message.content"),
    retrievedChunkIds: stringList(raw.retrieved_chunk_ids, "chat_message.retrieved_chunk_ids"),
    citations: mapCitations(raw.citations),
    metadata,
    createdAt: requireString(raw.created_at, "chat_message.created_at"),
    agentMetadata,
  };
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
