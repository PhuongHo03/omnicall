import { retryWithBackoff } from "../../../shared/utils/retryWithBackoff";
import { apiUrl, authHeaders, jsonHeaders, parseJsonResponse } from "../../../shared/utils/httpClient";
import { buildLoginPayload, buildRegisterPayload, parseAuthSession, parseMe } from "../dtos/authDtos";
import type { Account, AuthSession } from "../types/authTypes";

export async function registerAccount(
  email: string,
  password: string,
  displayName: string
): Promise<AuthSession> {
  const response = await fetch(apiUrl("/auth/register"), {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(buildRegisterPayload(email, password, displayName))
  });
  return parseAuthSession(await parseJsonResponse(response));
}

export async function loginAccount(email: string, password: string): Promise<AuthSession> {
  const response = await fetch(apiUrl("/auth/login"), {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(buildLoginPayload(email, password))
  });
  return parseAuthSession(await parseJsonResponse(response));
}

export async function logoutAccount(token: string): Promise<void> {
  await fetch(apiUrl("/auth/logout"), {
    method: "POST",
    headers: authHeaders(token)
  });
}

export async function getCurrentAccount(token: string): Promise<Account> {
  return retryWithBackoff(async () => {
    const response = await fetch(apiUrl("/me"), {
      headers: authHeaders(token)
    });
    return parseMe(await parseJsonResponse(response));
  }, { maxRetries: 2, baseDelayMs: 1000 });
}
