import { useCallback, useState } from "react";

import { isBooleanRecord } from "../utils/jsonDisplay";

const STORAGE_KEY = "omnicall:meeting-result-open-sections";

export function useResultSectionState() {
  const [sectionOpenState, setSectionOpenState] = useState<Record<string, boolean>>(() => readSectionOpenState());

  const updateSectionOpenState = useCallback((sectionKey: string, isOpen: boolean) => {
    setSectionOpenState((current) => {
      const next = { ...current, [sectionKey]: isOpen };
      writeSectionOpenState(next);
      return next;
    });
  }, []);

  return {
    sectionOpenState,
    updateSectionOpenState,
  };
}

function readSectionOpenState() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return {};
    const parsed = JSON.parse(stored);
    return isBooleanRecord(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function writeSectionOpenState(state: Record<string, boolean>) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Local storage persistence is optional for the viewer.
  }
}
