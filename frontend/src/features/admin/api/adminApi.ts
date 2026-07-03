import { parseAdminAccount, parseAdminAccounts, parseAdminMetrics, parseAdminOperationalLogs, parseAdminMeetingLogSummaries } from "../dtos/adminDtos";
import type {
  AdminAccount,
  AdminAccountList,
  AdminAccountRole,
  AdminLogFlow,
  AdminLogLevel,
  AdminMeetingLogSummary,
  AdminMetrics,
  AdminOperationalLogList
} from "../types/adminTypes";

const API_PREFIX = "/api";

function authHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`
  };
}

function jsonAuthHeaders(token: string): HeadersInit {
  return {
    ...authHeaders(token),
    "Content-Type": "application/json"
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

export async function getAdminMetrics(token: string): Promise<AdminMetrics> {
  const response = await fetch(`${API_PREFIX}/admin/metrics`, {
    headers: authHeaders(token)
  });
  return parseAdminMetrics(await parseJsonResponse(response));
}

export async function getAdminAccounts(token: string): Promise<AdminAccountList> {
  const response = await fetch(`${API_PREFIX}/admin/accounts`, {
    headers: authHeaders(token)
  });
  return parseAdminAccounts(await parseJsonResponse(response));
}

export async function updateAdminAccountRole(token: string, userId: string, role: AdminAccountRole): Promise<AdminAccount> {
  const response = await fetch(`${API_PREFIX}/admin/accounts/${userId}/role`, {
    method: "PATCH",
    headers: jsonAuthHeaders(token),
    body: JSON.stringify({ role })
  });
  return parseAdminAccount(await parseJsonResponse(response));
}

export async function deleteAdminAccount(token: string, userId: string): Promise<void> {
  const response = await fetch(`${API_PREFIX}/admin/accounts/${userId}`, {
    method: "DELETE",
    headers: authHeaders(token)
  });
  await parseJsonResponse(response);
}

export async function getAdminMeetingLogs(token: string): Promise<AdminMeetingLogSummary[]> {
  const response = await fetch(`${API_PREFIX}/admin/logs/meetings`, {
    headers: authHeaders(token),
    cache: "no-store"
  });
  return parseAdminMeetingLogSummaries(await parseJsonResponse(response));
}

export async function getAdminOperationalLogs(
  token: string,
  filters: {
    flow: AdminLogFlow;
    level: AdminLogLevel | "all";
    limit: number;
    search: string;
    meetingId?: string;
  }
): Promise<AdminOperationalLogList> {
  const query = new URLSearchParams({
    flow: filters.flow,
    limit: String(filters.limit)
  });
  if (filters.level !== "all") {
    query.set("level", filters.level);
  }
  if (filters.search.trim()) {
    query.set("search", filters.search.trim());
  }
  if (filters.meetingId) {
    query.set("meeting_id", filters.meetingId);
  }
  const response = await fetch(`${API_PREFIX}/admin/logs?${query.toString()}`, {
    headers: authHeaders(token),
    cache: "no-store"
  });
  return parseAdminOperationalLogs(await parseJsonResponse(response));
}

export async function clearAdminOperationalLogs(token: string, meetingId?: string): Promise<void> {
  const query = meetingId ? `?meeting_id=${encodeURIComponent(meetingId)}` : "";
  const response = await fetch(`${API_PREFIX}/admin/logs${query}`, {
    method: "DELETE",
    headers: authHeaders(token)
  });
  await parseJsonResponse(response);
}
