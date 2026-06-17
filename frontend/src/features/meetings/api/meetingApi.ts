import {
  buildChatPayload,
  buildMeetingPayload,
  parseAccountFile,
  parseAccountFileList,
  parseAsset,
  parseMeeting,
  parseMeetingChatHistory,
  parseMeetingChatResponse,
  parseMeetingIntelligenceResult,
  parseMeetingList,
  parseProcessingJob,
  parseProcessingStatus
} from "../dtos/meetingDtos";
import type {
  AccountFile,
  Meeting,
  MeetingAsset,
  MeetingChatHistory,
  MeetingChatResponse,
  MeetingIntelligenceResult,
  ProcessingJob,
  ProcessingStatus
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

export async function createMeeting(token: string, title: string, language: string): Promise<Meeting> {
  const response = await fetch(`${API_PREFIX}/meetings`, {
    method: "POST",
    headers: {
      ...authHeaders(token),
      "Content-Type": "application/json"
    },
    body: JSON.stringify(buildMeetingPayload(title, language))
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
): Promise<ProcessingJob> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/process`, {
    method: "POST",
    headers: {
      ...authHeaders(token),
      "Idempotency-Key": idempotencyKey
    }
  });
  return parseProcessingJob(await parseJsonResponse(response));
}

export async function getProcessingStatus(token: string, meetingId: string): Promise<ProcessingStatus> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/processing-status`, {
    headers: authHeaders(token)
  });
  return parseProcessingStatus(await parseJsonResponse(response));
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
  question: string,
  sessionId: string | null,
  language: string | null
): Promise<MeetingChatResponse> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/chat`, {
    method: "POST",
    headers: {
      ...authHeaders(token),
      "Content-Type": "application/json"
    },
    body: JSON.stringify(buildChatPayload(question, sessionId, language))
  });
  return parseMeetingChatResponse(await parseJsonResponse(response));
}

export async function getMeetingChatHistory(
  token: string,
  meetingId: string,
  sessionId: string
): Promise<MeetingChatHistory> {
  const response = await fetch(`${API_PREFIX}/meetings/${meetingId}/chat/${sessionId}`, {
    headers: authHeaders(token)
  });
  return parseMeetingChatHistory(await parseJsonResponse(response));
}

export async function listAccountFiles(token: string): Promise<AccountFile[]> {
  const response = await fetch(`${API_PREFIX}/files`, {
    headers: authHeaders(token)
  });
  return parseAccountFileList(await parseJsonResponse(response));
}

export async function uploadAccountFile(token: string, file: File): Promise<AccountFile> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_PREFIX}/files`, {
    method: "POST",
    headers: authHeaders(token),
    body: formData
  });
  return parseAccountFile(await parseJsonResponse(response));
}

export async function downloadAccountFile(token: string, fileId: string): Promise<Blob> {
  const response = await fetch(`${API_PREFIX}/files/${fileId}/content`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = typeof payload?.message === "string" ? payload.message : "File download failed.";
    throw new Error(message);
  }
  return response.blob();
}

export async function deleteAccountFile(token: string, fileId: string): Promise<void> {
  const response = await fetch(`${API_PREFIX}/files/${fileId}`, {
    method: "DELETE",
    headers: authHeaders(token)
  });
  await parseJsonResponse(response);
}

export async function deleteMeetingSession(token: string, meetingId: string): Promise<void> {
  const response = await fetch(`${API_PREFIX}/admin/meetings/${meetingId}`, {
    method: "DELETE",
    headers: authHeaders(token)
  });
  await parseJsonResponse(response);
}
