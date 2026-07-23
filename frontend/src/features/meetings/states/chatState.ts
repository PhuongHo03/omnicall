import { createClientId } from "../../../shared/utils/id";
import type { ChatFeedbackRating, MeetingChatMessage, PipelineTrace } from "../types/meetingTypes";

const FEEDBACK_ELIGIBLE_EVIDENCE_STATES = new Set([
  "grounded",
  "partial",
  "not_enough_evidence",
]);
const LIVE_PIPELINE_STAGES = new Set<PipelineTrace["stages"][number]["stage"]>([
  "request_gate", "query_interpretation", "retrieval", "evidence_validation",
  "synthesis", "answer_verification", "output_policy", "persistence",
]);

export function createOptimisticChatMessage(role: "user" | "assistant", content: string): MeetingChatMessage {
  return {
    id: `local:${createClientId()}`,
    role,
    content,
    retrievedChunkIds: [],
    citations: [],
    metadata: { local: true, pending: role === "assistant" },
    feedbackRating: null,
    feedbackRevision: 0,
    createdAt: new Date().toISOString(),
  };
}

export function isFeedbackEligibleMessage(message: MeetingChatMessage): boolean {
  if (
    message.role !== "assistant"
    || message.id.startsWith("local:")
    || message.metadata.local === true
    || message.metadata.pending === true
    || message.metadata.streaming === true
  ) {
    return false;
  }
  return message.metadata.feedbackEligible !== false
    && typeof message.metadata.evidenceState === "string"
    && FEEDBACK_ELIGIBLE_EVIDENCE_STATES.has(message.metadata.evidenceState);
}

export function toggledFeedbackSelection(
  current: ChatFeedbackRating | null,
  clicked: ChatFeedbackRating,
): ChatFeedbackRating | "neutral" {
  return current === clicked ? "neutral" : clicked;
}

export function restoreRejectedChatQuestion(currentDraft: string, submittedQuestion: string): string {
  return currentDraft.trim() ? currentDraft : submittedQuestion;
}

export function mergeChatHistory(
  current: MeetingChatMessage[],
  incoming: MeetingChatMessage[],
  pendingFeedbackMessageIds: ReadonlySet<string> = new Set(),
): MeetingChatMessage[] {
  const currentById = new Map(current.map((message) => [message.id, message]));
  return incoming.map((message) => {
    const existing = currentById.get(message.id);
    if (!existing) return message;

    const incomingIsNewer = message.feedbackRevision > existing.feedbackRevision;
    const preserveExistingFeedback = existing.feedbackRevision > message.feedbackRevision
      || (pendingFeedbackMessageIds.has(message.id) && !incomingIsNewer);
    if (!preserveExistingFeedback) return message;

    return {
      ...message,
      feedbackRating: existing.feedbackRating,
      feedbackRevision: existing.feedbackRevision,
      feedbackStatus: existing.feedbackStatus,
      feedbackCacheAction: existing.feedbackCacheAction,
    };
  });
}

export function completedAssistantMessageIds(messages: MeetingChatMessage[]): string[] {
  return messages
    .filter((message) => message.role === "assistant" && !message.metadata.pending)
    .map((message) => message.id);
}

export function appendLivePipelineStage(trace: PipelineTrace | undefined, stage: string): PipelineTrace | undefined {
  if (!LIVE_PIPELINE_STAGES.has(stage as PipelineTrace["stages"][number]["stage"])) return trace;
  const currentStage = stage as PipelineTrace["stages"][number]["stage"];
  const stages = (trace?.stages ?? []).map((item) => item.status === "in_progress"
    ? { ...item, status: "succeeded" }
    : item);
  if (stages.at(-1)?.stage === currentStage) return { version: 1, contract: "simple-rag.v1", stages };
  return {
    version: 1,
    contract: "simple-rag.v1",
    stages: [...stages, {
      stage: currentStage,
      status: "in_progress",
      durationMs: 0,
      provider: null,
      model: null,
      details: { live: true },
    }],
  };
}
