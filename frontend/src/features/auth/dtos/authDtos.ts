import type { Account, AuthSession } from "../types/authTypes";

type RawAccount = {
  user_id?: unknown;
  email?: unknown;
  display_name?: unknown;
  role?: unknown;
};

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string") {
    throw new Error(`Invalid ${field}.`);
  }
  return value;
}

function parseAccount(raw: RawAccount): Account {
  const role = requireString(raw.role, "account.role");
  return {
    userId: requireString(raw.user_id, "account.user_id"),
    email: requireString(raw.email, "account.email"),
    displayName: requireString(raw.display_name, "account.display_name"),
    role: role === "Admin" ? "Admin" : "User"
  };
}

export function parseAuthSession(raw: unknown): AuthSession {
  const payload = raw as { token?: unknown; expires_at?: unknown; account?: unknown };
  return {
    token: requireString(payload.token, "auth.token"),
    expiresAt: requireString(payload.expires_at, "auth.expires_at"),
    account: parseAccount(payload.account as RawAccount)
  };
}

export function parseMe(raw: unknown): Account {
  const payload = raw as { account?: unknown };
  return parseAccount(payload.account as RawAccount);
}

export function buildRegisterPayload(email: string, password: string, displayName: string) {
  return {
    email: email.trim(),
    password,
    display_name: displayName.trim()
  };
}

export function buildLoginPayload(email: string, password: string) {
  return {
    email: email.trim(),
    password
  };
}
