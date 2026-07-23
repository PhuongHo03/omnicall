import { apiUrl, authHeaders } from "../../../shared/utils/httpClient";
import { parseChatStreamEvent } from "../dtos/chatStreamDtos";
import type { ChatStreamEvent } from "../types/meetingTypes";

export type { ChatStreamEvent } from "../types/meetingTypes";

export function streamChatEvents(
  token: string,
  meetingId: string,
  turnId: string | undefined,
  onEvent: (event: ChatStreamEvent) => void,
  onError?: (error: Error) => void,
  onEnd?: () => void,
): () => void {
  const controller = new AbortController();
  const url = apiUrl(`/meetings/${meetingId}/chat/stream${turnId ? `?turn_id=${encodeURIComponent(turnId)}` : ""}`);

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
              const event = parseChatStreamEvent(JSON.parse(jsonStr));
              if (event) {
                onEvent(event);
              }
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
