import {
  buildMeetingPayload,
  buildChatPayload,
  parseAsset,
  parseMeetingChatHistory,
  parseMeetingChatResponse,
  parseMeeting,
  parseMeetingList,
  parseProcessingJob,
  parseProcessingStatus
} from "../dtos/meetingDtos";
import type {
  DevAuthContext,
  Meeting,
  MeetingAsset,
  MeetingChatHistory,
  MeetingChatResponse,
  ProcessingJob,
  ProcessingStatus
} from "../types/meetingTypes";

const API_PREFIX = "/api";

function authHeaders(context: DevAuthContext): HeadersInit {
  return {
    "X-User-ID": context.userId,
    "X-Workspace-ID": context.workspaceId,
    "X-User-Email": context.userEmail,
    "X-User-Name": context.userName,
    "X-Workspace-Name": context.workspaceName
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

export async function listMeetings(context: DevAuthContext): Promise<Meeting[]> {
  const response = await fetch(`${API_PREFIX}/meetings`, {
    headers: authHeaders(context)
  });
  return parseMeetingList(await parseJsonResponse(response));
}

export async function createMeeting(
  context: DevAuthContext,
  title: string,
  language: string
): Promise<Meeting> {
  const response = await fetch(`${API_PREFIX}/meetings`, {
    method: "POST",
    headers: {
      ...authHeaders(context),
      "Content-Type": "application/json"
    },
    body: JSON.stringify(buildMeetingPayload(title, language))
  });
  return parseMeeting(await parseJsonResponse(response));
}

export async function uploadMeetingAsset(
  context: DevAuthContext,
  meetingId: string,
  file: File,
  idempotencyKey: string
): Promise<MeetingAsset> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/assets`, {
    method: "POST",
    headers: {
      ...authHeaders(context),
      "Idempotency-Key": idempotencyKey
    },
    body: formData
  });
  return parseAsset(await parseJsonResponse(response));
}

export async function queueMeetingProcessing(
  context: DevAuthContext,
  meetingId: string,
  idempotencyKey: string
): Promise<ProcessingJob> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/process`, {
    method: "POST",
    headers: {
      ...authHeaders(context),
      "Idempotency-Key": idempotencyKey
    }
  });
  return parseProcessingJob(await parseJsonResponse(response));
}

export async function getProcessingStatus(
  context: DevAuthContext,
  meetingId: string
): Promise<ProcessingStatus> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/processing-status`, {
    headers: authHeaders(context)
  });
  return parseProcessingStatus(await parseJsonResponse(response));
}

export async function askMeetingChat(
  context: DevAuthContext,
  meetingId: string,
  question: string,
  sessionId: string | null,
  language: string | null
): Promise<MeetingChatResponse> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/chat`, {
    method: "POST",
    headers: {
      ...authHeaders(context),
      "Content-Type": "application/json"
    },
    body: JSON.stringify(buildChatPayload(question, sessionId, language))
  });
  return parseMeetingChatResponse(await parseJsonResponse(response));
}

export async function getMeetingChatHistory(
  context: DevAuthContext,
  meetingId: string,
  sessionId: string
): Promise<MeetingChatHistory> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/chat/${sessionId}`, {
    headers: authHeaders(context)
  });
  return parseMeetingChatHistory(await parseJsonResponse(response));
}
