import { createClientId } from "../../../shared/utils/id";
import type { MeetingChatMessage } from "../types/meetingTypes";

export function createOptimisticChatMessage(role: "user" | "assistant", content: string): MeetingChatMessage {
  return {
    id: `local:${createClientId()}`,
    role,
    content,
    retrievedChunkIds: [],
    citations: [],
    metadata: { local: true, pending: role === "assistant" },
    createdAt: new Date().toISOString(),
  };
}

export function formatAgentToolLabel(tool: string): string {
  const labels: Record<string, string> = {
    search_semantic: "tìm kiếm ngữ nghĩa",
    search_keyword: "tìm theo từ khóa",
    search_section: "lọc theo mục",
    get_summary: "tóm tắt cuộc họp",
  };
  return labels[tool] ?? tool;
}

export function formatAgentSearchMessage(tools: string[]): string {
  return "Đang tìm bằng chứng trong cuộc họp...";
}

export function formatAgentObservationMessage(resultCount: number): string {
  if (resultCount <= 0) {
    return "Đang kiểm tra kết quả tìm kiếm...";
  }
  return `Đã tìm thấy ${resultCount} đoạn liên quan`;
}

export function completedAssistantMessageIds(messages: MeetingChatMessage[]): string[] {
  return messages
    .filter((message) => message.role === "assistant" && !message.metadata.pending)
    .map((message) => message.id);
}
