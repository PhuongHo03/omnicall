import { buildLoginPayload, buildRegisterPayload, parseAuthSession, parseMe } from "../dtos/authDtos";
import type { Account, AuthSession } from "../types/authTypes";

const API_PREFIX = "/api";

async function parseJsonResponse(response: Response): Promise<unknown> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = apiErrorMessage(payload);
    throw new Error(message);
  }
  return payload;
}

function apiErrorMessage(payload: unknown): string {
  if (!payload || typeof payload !== "object") {
    return "Request failed.";
  }
  if ("message" in payload && typeof payload.message === "string") {
    return payload.message;
  }
  if ("detail" in payload && Array.isArray(payload.detail)) {
    const firstDetail = payload.detail[0] as { msg?: unknown; loc?: unknown } | undefined;
    if (firstDetail && typeof firstDetail.msg === "string") {
      const location = Array.isArray(firstDetail.loc) ? firstDetail.loc.filter((item) => item !== "body").join(".") : "";
      return location ? `${location}: ${firstDetail.msg}` : firstDetail.msg;
    }
  }
  if ("detail" in payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  return "Request failed.";
}

export async function registerAccount(
  email: string,
  password: string,
  displayName: string,
  role: string
): Promise<AuthSession> {
  const response = await fetch(`${API_PREFIX}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildRegisterPayload(email, password, displayName, role))
  });
  return parseAuthSession(await parseJsonResponse(response));
}

export async function loginAccount(email: string, password: string): Promise<AuthSession> {
  const response = await fetch(`${API_PREFIX}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildLoginPayload(email, password))
  });
  return parseAuthSession(await parseJsonResponse(response));
}

export async function logoutAccount(token: string): Promise<void> {
  await fetch(`${API_PREFIX}/auth/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` }
  });
}

export async function getCurrentAccount(token: string): Promise<Account> {
  const response = await fetch(`${API_PREFIX}/me`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  return parseMe(await parseJsonResponse(response));
}
