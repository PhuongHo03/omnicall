import { useMemo } from "react";

import type { TranscriptEntry } from "../types/meetingTypes";

export type TranscriptSyncState = {
  activeIndex: number;
  activeEntry: TranscriptEntry | null;
  progressWithinEntry: number;
};

export function useTranscriptSync(
  entries: TranscriptEntry[],
  currentTimeSeconds: number
): TranscriptSyncState {
  const currentTimeMs = currentTimeSeconds * 1000;

  const activeIndex = useMemo(() => {
    if (entries.length === 0) return -1;
    for (let i = 0; i < entries.length; i++) {
      const entry = entries[i];
      if (currentTimeMs >= entry.startMs && currentTimeMs < entry.endMs) {
        return i;
      }
    }
    // If past all entries, highlight the last one
    if (currentTimeMs >= entries[entries.length - 1].endMs) {
      return entries.length - 1;
    }
    return -1;
  }, [entries, currentTimeMs]);

  const activeEntry = activeIndex >= 0 ? entries[activeIndex] : null;

  const progressWithinEntry = useMemo(() => {
    if (!activeEntry) return 0;
    const duration = activeEntry.endMs - activeEntry.startMs;
    if (duration <= 0) return 0;
    return Math.max(0, Math.min(1, (currentTimeMs - activeEntry.startMs) / duration));
  }, [activeEntry, currentTimeMs]);

  return { activeIndex, activeEntry, progressWithinEntry };
}
