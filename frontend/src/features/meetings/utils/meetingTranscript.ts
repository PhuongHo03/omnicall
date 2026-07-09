import type { MeetingIntelligenceResult, TranscriptEntry } from "../types/meetingTypes";

export function extractTranscriptEntries(intelligenceResult: MeetingIntelligenceResult | null): TranscriptEntry[] {
  if (!intelligenceResult || typeof intelligenceResult !== "object") return [];
  const transcript = (intelligenceResult as Record<string, unknown>).transcript;
  if (!transcript || typeof transcript !== "object") return [];
  const segments = (transcript as Record<string, unknown>).segments;
  if (!Array.isArray(segments)) return [];
  return segments
    .map((seg: unknown) => {
      const s = seg as Record<string, unknown>;
      return {
        id: String(s.id ?? ""),
        speaker: String(s.speaker ?? "Unknown"),
        startMs: typeof s.startMs === "number" ? s.startMs : 0,
        endMs: typeof s.endMs === "number" ? s.endMs : 0,
        text: String(s.text ?? ""),
      };
    })
    .filter((entry) => entry.id && entry.text);
}
