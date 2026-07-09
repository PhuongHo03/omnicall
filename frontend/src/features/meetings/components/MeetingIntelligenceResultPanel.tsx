import { useMemo } from "react";

import type { MeetingIntelligenceResult } from "../types/meetingTypes";
import { stringValue } from "../utils/jsonDisplay";
import { useResultSectionState } from "../hooks/useResultSectionState";
import { JsonSection } from "./JsonSection";

type MeetingIntelligenceResultPanelProps = {
  result: MeetingIntelligenceResult;
};

const SECTION_ORDER = ["meeting", "source", "participants", "summary", "analysis", "transcript", "citations", "quality"];
const DEFAULT_OPEN_SECTIONS = new Set<string>();

export function MeetingIntelligenceResultPanel({ result }: MeetingIntelligenceResultPanelProps) {
  const { sectionOpenState, updateSectionOpenState } = useResultSectionState();
  const sectionKeys = useMemo(
    () =>
      result
        ? [
            ...SECTION_ORDER.filter((key) => key in result),
            ...Object.keys(result).filter((key) => !SECTION_ORDER.includes(key))
          ]
        : [],
    [result]
  );

  return (
    <section className="result-panel">
      <div className="result-panel__header">
        <span className="result-panel__version">{stringValue(result.schemaVersion) || "meeting-intelligence-result"}</span>
      </div>
      <div className="json-section-list">
        {sectionKeys.map((key) => (
          <JsonSection
            key={key}
            isOpen={sectionOpenState[key] ?? DEFAULT_OPEN_SECTIONS.has(key)}
            sectionKey={key}
            value={result[key]}
            onToggle={(isOpen) => updateSectionOpenState(key, isOpen)}
          />
        ))}
      </div>
    </section>
  );
}
