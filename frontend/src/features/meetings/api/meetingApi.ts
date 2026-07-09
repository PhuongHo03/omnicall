import { apiUrl, authHeaders, jsonHeaders, parseBlobResponse, parseJsonResponse } from "../../../shared/utils/httpClient";
import { retryWithBackoff } from "../../../shared/utils/retryWithBackoff";
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

export async function uploadMeetingAsset(
  token: string,
  meetingId: string,
  file: File,
  idempotencyKey: string
): Promise<MeetingAsset> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(apiUrl(`/meetings/${meetingId}/assets`), {
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

export async function downloadMeetingAsset(token: string, meetingId: string, assetId: string): Promise<Blob> {
  const response = await fetch(apiUrl(`/meetings/${meetingId}/assets/${assetId}/content`), {
    headers: authHeaders(token)
  });
  return parseBlobResponse(response, "Asset download failed.");
}

const CHAT_POST_TIMEOUT_MS = 30_000;

export async function askMeetingChat(
  token: string,
  meetingId: string,
  question: string
): Promise<{ status: string; message: string }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CHAT_POST_TIMEOUT_MS);
  try {
    const response = await fetch(apiUrl(`/meetings/${meetingId}/chat`), {
      method: "POST",
      headers: jsonHeaders(token),
      body: JSON.stringify(buildChatPayload(question)),
      signal: controller.signal
    });
    return parseJsonResponse(response) as Promise<{ status: string; message: string }>;
  } finally {
    clearTimeout(timeoutId);
  }
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
