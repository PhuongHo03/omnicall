import { apiErrorMessage, apiUrl, authHeaders, jsonHeaders, parseBlobResponse, parseJsonResponse } from "../../../shared/utils/httpClient";
import { retryWithBackoff } from "../../../shared/utils/retryWithBackoff";
import {
  buildChatPayload,
  buildChatFeedbackPayload,
  buildMeetingTitlePayload,
  parseChatFeedbackResponse,
  parseAsset,
  parseMeeting,
  parseMeetingChatAccepted,
  parseMeetingChatHistory,
  parseMeetingIntelligenceResult,
  parseMeetingList,
} from "../dtos/meetingDtos";
import type {
  ChatFeedbackResult,
  ChatFeedbackSelection,
  Meeting,
  MeetingAsset,
  MeetingChatAcceptedResult,
  MeetingChatHistory,
  MeetingIntelligenceResult,
} from "../types/meetingTypes";

export async function listMeetings(token: string, options?: { signal?: AbortSignal }): Promise<Meeting[]> {
  return retryWithBackoff(async () => {
    const response = await fetch(apiUrl("/meetings"), {
      headers: authHeaders(token),
      signal: options?.signal
    });
    return parseMeetingList(await parseJsonResponse(response));
  }, { maxRetries: 2, baseDelayMs: 1000 });
}

export async function getMeeting(token: string, meetingId: string, options?: { signal?: AbortSignal }): Promise<Meeting> {
  return retryWithBackoff(async () => {
    const response = await fetch(apiUrl(`/meetings/${meetingId}`), {
      headers: authHeaders(token),
      signal: options?.signal
    });
    return parseMeeting(await parseJsonResponse(response));
  }, { maxRetries: 2, baseDelayMs: 1000 });
}

export async function createMeeting(token: string): Promise<Meeting> {
  const response = await fetch(apiUrl("/meetings"), {
    method: "POST",
    headers: jsonHeaders(token),
    body: JSON.stringify({})
  });
  return parseMeeting(await parseJsonResponse(response));
}

export async function updateMeetingTitle(token: string, meetingId: string, title: string): Promise<Meeting> {
  const response = await fetch(apiUrl(`/meetings/${meetingId}`), {
    method: "PATCH",
    headers: jsonHeaders(token),
    body: JSON.stringify(buildMeetingTitlePayload(title))
  });
  return parseMeeting(await parseJsonResponse(response));
}

export async function setChatFeedback(
  token: string,
  meetingId: string,
  messageId: string,
  rating: ChatFeedbackSelection,
  expectedRevision?: number,
): Promise<ChatFeedbackResult> {
  const response = await fetch(apiUrl(`/meetings/${meetingId}/chat/messages/${messageId}/feedback`), {
    method: "PUT",
    headers: jsonHeaders(token),
    body: JSON.stringify(buildChatFeedbackPayload(rating, expectedRevision)),
  });
  return parseChatFeedbackResponse(await parseJsonResponse(response));
}

export async function uploadMeetingAsset(
  token: string,
  meetingId: string,
  file: File,
  idempotencyKey: string,
  onProgress?: (progress: number) => void,
): Promise<MeetingAsset> {
  const formData = new FormData();
  formData.append("file", file);

  const payload = await new Promise<unknown>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", apiUrl(`/meetings/${meetingId}/assets`));
    request.setRequestHeader("Authorization", `Bearer ${token}`);
    request.setRequestHeader("Idempotency-Key", idempotencyKey);
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress?.((event.loaded / event.total) * 100);
      }
    });
    request.addEventListener("load", () => {
      const responsePayload = (() => {
        try {
          return JSON.parse(request.responseText) as unknown;
        } catch {
          return null;
        }
      })();
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(100);
        resolve(responsePayload);
        return;
      }
      reject(new Error(apiErrorMessage(responsePayload, "Upload failed.")));
    });
    request.addEventListener("error", () => reject(new Error("Upload failed.")));
    request.addEventListener("abort", () => reject(new Error("Upload was cancelled.")));
    request.send(formData);
  });
  return parseAsset(payload);
}

export async function queueMeetingProcessing(
  token: string,
  meetingId: string,
  idempotencyKey: string
): Promise<Meeting> {
  const response = await fetch(apiUrl(`/meetings/${meetingId}/process`), {
    method: "POST",
    headers: {
      ...authHeaders(token),
      "Idempotency-Key": idempotencyKey
    }
  });
  return parseMeeting(await parseJsonResponse(response));
}


export async function getMeetingIntelligenceResult(token: string, meetingId: string, options?: { signal?: AbortSignal }): Promise<MeetingIntelligenceResult> {
  const response = await fetch(apiUrl(`/meetings/${meetingId}/intelligence-result`), {
    headers: authHeaders(token),
    signal: options?.signal
  });
  return parseMeetingIntelligenceResult(await parseJsonResponse(response));
}

export async function downloadMeetingAsset(token: string, meetingId: string, assetId: string, options?: { signal?: AbortSignal }): Promise<Blob> {
  const response = await fetch(apiUrl(`/meetings/${meetingId}/assets/${assetId}/content`), {
    headers: authHeaders(token),
    signal: options?.signal,
  });
  return parseBlobResponse(response, "Asset download failed.");
}

const CHAT_POST_TIMEOUT_MS = 30_000;

export async function askMeetingChat(
  token: string,
  meetingId: string,
  question: string
): Promise<MeetingChatAcceptedResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CHAT_POST_TIMEOUT_MS);
  try {
    const response = await fetch(apiUrl(`/meetings/${meetingId}/chat`), {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(buildChatPayload(question)),
      signal: controller.signal
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const code = payload && typeof payload === "object" && "code" in payload && typeof payload.code === "string"
        ? payload.code
        : "request_failed";
      throw new MeetingChatApiError(response.status, code, apiErrorMessage(payload));
    }
    return parseMeetingChatAccepted(payload);
  } finally {
    clearTimeout(timeoutId);
  }
}

export class MeetingChatApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "MeetingChatApiError";
    this.status = status;
    this.code = code;
  }
}

export function isChatBusyError(caught: unknown): caught is MeetingChatApiError {
  return caught instanceof MeetingChatApiError
    && caught.status === 409
    && caught.code === "chat_busy";
}

export async function getMeetingChatHistory(token: string, meetingId: string, options?: { signal?: AbortSignal }): Promise<MeetingChatHistory> {
  return retryWithBackoff(async () => {
    const response = await fetch(apiUrl(`/meetings/${meetingId}/chat`), {
      headers: authHeaders(token),
      signal: options?.signal
    });
    return parseMeetingChatHistory(await parseJsonResponse(response));
  }, { maxRetries: 2, baseDelayMs: 1000 });
}

export { streamChatEvents } from "./chatStreamApi";
export type { ChatStreamEvent } from "./chatStreamApi";

export async function deleteMeetingSession(token: string, meetingId: string): Promise<void> {
  const response = await fetch(apiUrl(`/meetings/${meetingId}`), {
    method: "DELETE",
    headers: authHeaders(token)
  });
  await parseJsonResponse(response);
}
