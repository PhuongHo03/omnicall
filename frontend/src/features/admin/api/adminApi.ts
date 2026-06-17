import { parseAdminMetrics } from "../dtos/adminDtos";
import type { AdminMetrics } from "../types/adminTypes";

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

export async function getAdminMetrics(token: string): Promise<AdminMetrics> {
  const response = await fetch(`${API_PREFIX}/admin/metrics`, {
    headers: authHeaders(token)
  });
  return parseAdminMetrics(await parseJsonResponse(response));
}
