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
    search_speaker: "tìm theo người nói",
    get_summary: "tóm tắt cuộc họp",
    get_action_items: "việc cần làm",
    get_decisions: "quyết định",
    get_risks: "rủi ro",
    get_timeline: "mốc thời gian",
    get_participants: "người tham gia",
  };
  return labels[tool] ?? tool;
}

export function formatAgentSearchMessage(tools: string[]): string {
  if (tools.length === 0) {
    return "Đang tìm bằng chứng trong cuộc họp...";
  }
  return `Đang tìm bằng ${tools.map(formatAgentToolLabel).join(", ")}...`;
}

export function completedAssistantMessageIds(messages: MeetingChatMessage[]): string[] {
  return messages
    .filter((message) => message.role === "assistant" && !message.metadata.pending)
    .map((message) => message.id);
}
