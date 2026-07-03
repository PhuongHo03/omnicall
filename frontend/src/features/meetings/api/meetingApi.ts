import {
  buildChatPayload,
  buildMeetingTitlePayload,
  parseAsset,
  parseMeeting,
  parseMeetingChatHistory,
  parseMeetingIntelligenceResult,
  parseMeetingList,
} from "../dtos/meetingDtos";
import type {
  Meeting,
  MeetingAsset,
  MeetingChatHistory,
  MeetingIntelligenceResult,
} from "../types/meetingTypes";

const API_PREFIX = "/api";

function authHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`
  };
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof payload?.message === "string" ? payload.message : "Request failed.";
    throw new Error(message);
  }
  return payload;
}

export async function listMeetings(token: string): Promise<Meeting[]> {
  const response = await fetch(`${API_PREFIX}/meetings`, {
    headers: authHeaders(token)
  });
  return parseMeetingList(await parseJsonResponse(response));
}

export async function getMeeting(token: string, meetingId: string): Promise<Meeting> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}`, {
    headers: authHeaders(token)
  });
  return parseMeeting(await parseJsonResponse(response));
}

export async function createMeeting(token: string): Promise<Meeting> {
  const response = await fetch(`${API_PREFIX}/meetings`, {
    method: "POST",
    headers: {
      ...authHeaders(token),
      "Content-Type": "application/json"
    },
    body: JSON.stringify({})
  });
  return parseMeeting(await parseJsonResponse(response));
}

export async function updateMeetingTitle(token: string, meetingId: string, title: string): Promise<Meeting> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}`, {
    method: "PATCH",
    headers: {
      ...authHeaders(token),
      "Content-Type": "application/json"
    },
    body: JSON.stringify(buildMeetingTitlePayload(title))
  });
  return parseMeeting(await parseJsonResponse(response));
}

export async function uploadMeetingAsset(
  token: string,
  meetingId: string,
  file: File,
  idempotencyKey: string
): Promise<MeetingAsset> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/assets`, {
    method: "POST",
    headers: {
      ...authHeaders(token),
      "Idempotency-Key": idempotencyKey
    },
    body: formData
  });
  return parseAsset(await parseJsonResponse(response));
}

export async function queueMeetingProcessing(
  token: string,
  meetingId: string,
  idempotencyKey: string
): Promise<Meeting> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/process`, {
    method: "POST",
    headers: {
      ...authHeaders(token),
      "Idempotency-Key": idempotencyKey
    }
  });
  return parseMeeting(await parseJsonResponse(response));
}


export async function getMeetingIntelligenceResult(token: string, meetingId: string): Promise<MeetingIntelligenceResult> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/intelligence-result`, {
    headers: authHeaders(token)
  });
  return parseMeetingIntelligenceResult(await parseJsonResponse(response));
}

export async function downloadMeetingAsset(token: string, meetingId: string, assetId: string): Promise<Blob> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/assets/${assetId}/content`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = typeof payload?.message === "string" ? payload.message : "Asset download failed.";
    throw new Error(message);
  }
  return response.blob();
}

export async function askMeetingChat(
  token: string,
  meetingId: string,
  question: string
): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/chat`, {
    method: "POST",
    headers: {
      ...authHeaders(token),
      "Content-Type": "application/json"
    },
    body: JSON.stringify(buildChatPayload(question))
  });
  return parseJsonResponse(response) as Promise<{ status: string; message: string }>;
}

export async function getMeetingChatHistory(token: string, meetingId: string): Promise<MeetingChatHistory> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/chat`, {
    headers: authHeaders(token)
  });
  return parseMeetingChatHistory(await parseJsonResponse(response));
}





export type ChatStreamEvent =
  | { type: "status"; stage: string; message: string }
  | { type: "token"; token: string }
  | { type: "done"; answer: string }
  | { type: "blocked"; message: string }
  | { type: "error"; message: string }
  | { type: "connected"; status: string };

export function streamChatEvents(
  token: string,
  meetingId: string,
  onEvent: (event: ChatStreamEvent) => void,
  onError?: (error: Error) => void,
  onEnd?: () => void,
): () => void {
  const controller = new AbortController();
  const url = `${API_PREFIX}/meetings/${meetingId}/chat/stream`;

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
              // skip malformed events
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

export async function deleteMeetingSession(token: string, meetingId: string): Promise<void> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}`, {
    method: "DELETE",
    headers: authHeaders(token)
  });
  await parseJsonResponse(response);
}
