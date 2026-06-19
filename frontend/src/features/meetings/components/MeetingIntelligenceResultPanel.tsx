import { useCallback, useMemo, useState } from "react";

import type { MeetingIntelligenceResult } from "../types/meetingTypes";

type MeetingIntelligenceResultPanelProps = {
  result: MeetingIntelligenceResult | null;
};

const SECTION_ORDER = ["meeting", "source", "participants", "summary", "analysis", "transcript", "citations", "quality"];
const DEFAULT_OPEN_SECTIONS = new Set(["summary", "analysis", "quality"]);
const STORAGE_KEY = "omnicall:meeting-result-open-sections";

export function MeetingIntelligenceResultPanel({ result }: MeetingIntelligenceResultPanelProps) {
  const [sectionOpenState, setSectionOpenState] = useState<Record<string, boolean>>(() => readSectionOpenState());
  const updateSectionOpenState = useCallback((sectionKey: string, isOpen: boolean) => {
    setSectionOpenState((current) => {
      const next = { ...current, [sectionKey]: isOpen };
      writeSectionOpenState(next);
      return next;
    });
  }, []);
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

  if (!result) {
    return (
      <section className="result-panel result-panel--empty">
        <div className="empty-panel">No processed result yet.</div>
      </section>
    );
  }

  return (
    <section className="result-panel">
      <div className="section-heading">
        <h2>Processed JSON</h2>
        <span>{stringValue(result.schemaVersion) || "meeting-intelligence-result"}</span>
      </div>
      <div className="json-section-list">
        {sectionKeys.map((key) => (
          <JsonSection
            key={key}
            isOpen={sectionOpenState[key] ?? DEFAULT_OPEN_SECTIONS.has(key)}
            title={labelize(key)}
            value={result[key]}
            onToggle={(isOpen) => updateSectionOpenState(key, isOpen)}
          />
        ))}
      </div>
    </section>
  );
}

function JsonSection({
  isOpen,
  onToggle,
  title,
  value
}: {
  isOpen: boolean;
  onToggle: (isOpen: boolean) => void;
  title: string;
  value: unknown;
}) {
  return (
    <details className="json-section" open={isOpen} onToggle={(event) => onToggle(event.currentTarget.open)}>
      <summary>{title}</summary>
      <div className="json-section__body">
        <JsonValue value={value} depth={0} />
      </div>
    </details>
  );
}

function JsonValue({ value, depth }: { value: unknown; depth: number }) {
  if (value === null || value === undefined) {
    return <span className="json-muted">null</span>;
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <span className="json-scalar">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="json-muted">Empty</span>;
    }
    return (
      <ol className="json-list">
        {value.map((item, index) => (
          <li key={index}>
            <JsonValue value={item} depth={depth + 1} />
          </li>
        ))}
      </ol>
    );
  }
  if (isRecord(value)) {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return <span className="json-muted">Empty</span>;
    }
    return (
      <dl className={depth > 1 ? "json-map json-map--compact" : "json-map"}>
        {entries.map(([key, entryValue]) => (
          <div key={key} className="json-map__row">
            <dt>{labelize(key)}</dt>
            <dd>
              <JsonValue value={entryValue} depth={depth + 1} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span className="json-scalar">{String(value)}</span>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function readSectionOpenState() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return {};
    }
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
    // The accordion still works for the current render if browser storage is unavailable.
  }
}

function isBooleanRecord(value: unknown): value is Record<string, boolean> {
  if (!isRecord(value)) {
    return false;
  }
  return Object.values(value).every((entry) => typeof entry === "boolean");
}

function labelize(value: string) {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
