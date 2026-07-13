import { useMemo } from "react";

import type { MeetingIntelligenceResult } from "../types/meetingTypes";
import { stringValue } from "../utils/jsonDisplay";
import { useResultSectionState } from "../hooks/useResultSectionState";
import { JsonSection } from "./JsonSection";

type MeetingIntelligenceResultPanelProps = {
  result: MeetingIntelligenceResult;
};

const SECTION_ORDER = [
  "meeting",
  "source",
  "transcript",
  "evidence",
  "speakers",
  "participants",
  "entities",
  "facts",
  "events",
  "relationships",
  "topics",
  "summaries",
  "actions",
  "decisions",
  "risks",
  "questions",
  "quality",
  "extraction"
];
const DEFAULT_OPEN_SECTIONS = new Set<string>();

export function MeetingIntelligenceResultPanel({ result }: MeetingIntelligenceResultPanelProps) {
  const { sectionOpenState, updateSectionOpenState } = useResultSectionState();
  const displayResult = useMemo(() => toDisplaySections(result), [result]);
  const sectionKeys = useMemo(
    () =>
      displayResult
        ? [
            ...SECTION_ORDER.filter((key) => key in displayResult),
            ...Object.keys(displayResult).filter((key) => !SECTION_ORDER.includes(key))
          ]
        : [],
    [displayResult]
  );

  return (
    <section className="result-panel">
      <div className="result-panel__header">
        <span className="result-panel__version">{stringValue(displayResult.schemaVersion) || "meeting-intelligence-result"}</span>
      </div>
      <div className="json-section-list">
        {sectionKeys.map((key) => (
          <JsonSection
            key={key}
            isOpen={sectionOpenState[key] ?? DEFAULT_OPEN_SECTIONS.has(key)}
            sectionKey={key}
            value={displayResult[key]}
            onToggle={(isOpen) => updateSectionOpenState(key, isOpen)}
          />
        ))}
      </div>
    </section>
  );
}

function toDisplaySections(result: MeetingIntelligenceResult): MeetingIntelligenceResult {
  const knowledge = result.knowledge;
  if (!knowledge || typeof knowledge !== "object" || Array.isArray(knowledge)) {
    return result;
  }
  const records = (knowledge as { records?: unknown }).records;
  if (!Array.isArray(records)) return result;
  const display: MeetingIntelligenceResult = { ...result };
  const sections = ["participants", "entities", "facts", "events", "topics", "actions", "decisions", "risks", "questions"];
  for (const section of sections) display[section] = [];
  for (const record of records) {
    if (!record || typeof record !== "object" || Array.isArray(record)) continue;
    const item = record as { type?: unknown; id?: unknown; data?: unknown; citationIds?: unknown; confidence?: unknown };
    const section = typeof item.type === "string" ? `${item.type}s` : "";
    if (!sections.includes(section)) continue;
    const data = item.data && typeof item.data === "object" && !Array.isArray(item.data) ? { ...(item.data as Record<string, unknown>) } : {};
    data.id = item.id;
    data.citationIds = item.citationIds;
    data.confidence = item.confidence;
    (display[section] as unknown[]).push(data);
  }
  display.relationships = (knowledge as { relationships?: unknown }).relationships ?? [];
  return display;
}
