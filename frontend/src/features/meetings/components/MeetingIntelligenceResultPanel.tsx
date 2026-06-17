import type { MeetingIntelligenceResult } from "../types/meetingTypes";

type MeetingIntelligenceResultPanelProps = {
  result: MeetingIntelligenceResult | null;
};

const SECTION_ORDER = ["meeting", "source", "participants", "summary", "analysis", "transcript", "citations", "quality"];

export function MeetingIntelligenceResultPanel({ result }: MeetingIntelligenceResultPanelProps) {
  if (!result) {
    return (
      <section className="result-panel result-panel--empty">
        <div className="empty-panel">No processed result yet.</div>
      </section>
    );
  }

  const sectionKeys = [
    ...SECTION_ORDER.filter((key) => key in result),
    ...Object.keys(result).filter((key) => !SECTION_ORDER.includes(key))
  ];

  return (
    <section className="result-panel">
      <div className="section-heading">
        <h2>Processed JSON</h2>
        <span>{stringValue(result.schemaVersion) || "meeting-intelligence-result"}</span>
      </div>
      <div className="json-section-list">
        {sectionKeys.map((key) => (
          <JsonSection key={key} title={labelize(key)} value={result[key]} />
        ))}
      </div>
    </section>
  );
}

function JsonSection({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="json-section" open={title === "Summary" || title === "Analysis" || title === "Quality"}>
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

function labelize(value: string) {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
