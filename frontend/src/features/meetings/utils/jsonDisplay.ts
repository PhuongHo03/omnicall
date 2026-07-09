export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function formatNumber(value: number): string {
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toFixed(2);
}

export function getArrayOrObjectCount(value: unknown): number | null {
  if (Array.isArray(value)) return value.length;
  if (isRecord(value)) {
    const keys = Object.keys(value);
    return keys.length > 0 ? keys.length : null;
  }
  return null;
}

export function isBooleanRecord(value: unknown): value is Record<string, boolean> {
  if (!isRecord(value)) return false;
  return Object.values(value).every((entry) => typeof entry === "boolean");
}

export function labelize(value: string): string {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
