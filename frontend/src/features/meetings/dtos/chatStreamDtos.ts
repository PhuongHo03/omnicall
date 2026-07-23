import { parseMeetingChatMessage } from "./meetingDtos";
import type { ChatStreamEvent } from "../types/meetingTypes";

export function parseChatStreamEvent(value: unknown): ChatStreamEvent | null {
  if (!isRecord(value) || typeof value.type !== "string") return null;
  if (value.type === "status") {
    return typeof value.turnId === "string" && typeof value.stage === "string" && typeof value.message === "string"
      ? { type: "status", turnId: value.turnId, stage: value.stage, message: value.message }
      : null;
  }
  if (value.type === "token") return typeof value.token === "string" ? { type: "token", token: value.token } : null;
  if (value.type === "done") {
    return typeof value.turnId === "string" && typeof value.answer === "string"
      ? withAssistantMessage({ type: "done", turnId: value.turnId, answer: value.answer }, value.assistantMessage)
      : null;
  }
  if (value.type === "clarification" || value.type === "clarification_needed" || value.type === "blocked") {
    return typeof value.turnId === "string" && typeof value.message === "string"
      ? withAssistantMessage({ type: value.type, turnId: value.turnId, message: value.message }, value.assistantMessage)
      : null;
  }
  if (value.type === "error") return typeof value.turnId === "string" && typeof value.message === "string" ? { type: "error", turnId: value.turnId, message: value.message } : null;
  if (value.type === "connected") return typeof value.status === "string" ? { type: "connected", status: value.status } : null;
  return null;
}

function withAssistantMessage<T extends ChatStreamEvent>(event: T, value: unknown): T {
  if (value === undefined) return event;
  try {
    return { ...event, assistantMessage: parseMeetingChatMessage(value) } as T;
  } catch {
    return event;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
