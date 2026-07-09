export const API_PREFIX = "/api";

export function apiUrl(path: string): string {
  return `${API_PREFIX}${path}`;
}

export function authHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
  };
}

export function jsonHeaders(token?: string): HeadersInit {
  return {
    ...(token ? authHeaders(token) : {}),
    "Content-Type": "application/json",
  };
}

export async function parseJsonResponse(response: Response): Promise<unknown> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(apiErrorMessage(payload));
  }
  return payload;
}

export async function parseBlobResponse(response: Response, fallbackMessage = "Download failed."): Promise<Blob> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(apiErrorMessage(payload, fallbackMessage));
  }
  return response.blob();
}

export function apiErrorMessage(payload: unknown, fallbackMessage = "Request failed."): string {
  if (!payload || typeof payload !== "object") {
    return fallbackMessage;
  }
  if ("message" in payload && typeof payload.message === "string") {
    return payload.message;
  }
  if ("detail" in payload && Array.isArray(payload.detail)) {
    const firstDetail = payload.detail[0] as { msg?: unknown; loc?: unknown } | undefined;
    if (firstDetail && typeof firstDetail.msg === "string") {
      const location = Array.isArray(firstDetail.loc)
        ? firstDetail.loc.filter((item) => item !== "body").join(".")
        : "";
      return location ? `${location}: ${firstDetail.msg}` : firstDetail.msg;
    }
  }
  if ("detail" in payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  return fallbackMessage;
}
