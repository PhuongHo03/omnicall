import type { MeetingChatCitation } from "../types/meetingTypes";

export function formatSectionType(sectionType: string): string {
  return sectionType
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatCitationKind(citation: MeetingChatCitation): string {
  const range = formatRange(citation.startMs, citation.endMs);
  if (range !== "section") {
    return range;
  }
  if (citation.sourceType === "metadata") {
    return "metadata";
  }
  if (citation.sourceType === "structured") {
    return "section";
  }
  return citation.sourceType;
}

export function formatRange(startMs: number | null, endMs: number | null): string {
  if (startMs === null && endMs === null) {
    return "section";
  }
  return `${formatMs(startMs)}-${formatMs(endMs)}`;
}

function formatMs(value: number | null): string {
  if (value === null || value < 0) {
    return "?";
  }
  const totalSeconds = Math.floor(value / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
