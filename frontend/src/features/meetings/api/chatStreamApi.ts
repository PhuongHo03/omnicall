import { apiUrl, authHeaders } from "../../../shared/utils/httpClient";

export type ChatStreamEvent =
  | { type: "status"; stage: string; message: string }
  | { type: "token"; token: string }
  | { type: "done"; answer: string }
  | { type: "blocked"; message: string }
  | { type: "error"; message: string }
  | { type: "connected"; status: string }
  | { type: "agent_think"; iteration: number; message: string }
  | { type: "agent_search"; iteration: number; tools: string[]; message?: string }
  | { type: "observation"; iteration: number; resultCount?: number; successCount?: number; failureCount?: number; tool_results?: Record<string, number>; total_chunks?: number }
  | { type: "agent_synthesize"; iteration?: number; forced?: boolean; message?: string }
  | { type: "fast_path"; intent?: string; message: string };

export function streamChatEvents(
  token: string,
  meetingId: string,
  onEvent: (event: ChatStreamEvent) => void,
  onError?: (error: Error) => void,
  onEnd?: () => void,
): () => void {
  const controller = new AbortController();
  const url = apiUrl(`/meetings/${meetingId}/chat/stream`);

  fetch(url, {
    headers: authHeaders(token),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`SSE connection failed: ${response.status}`);
      }
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("ReadableStream not supported");
      }
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith("event:") || trimmed.startsWith("retry:")) {
            continue;
          }
          if (trimmed.startsWith("data: ")) {
            const jsonStr = trimmed.slice(6);
            try {
              const event = JSON.parse(jsonStr) as ChatStreamEvent;
              onEvent(event);
            } catch {
              // Skip malformed events; polling will still recover persisted chat history.
            }
          }
        }
      }
      onEnd?.();
    })
    .catch((caught) => {
      if (caught instanceof Error && caught.name !== "AbortError") {
        onError?.(caught);
      }
    });

  return () => controller.abort();
}
