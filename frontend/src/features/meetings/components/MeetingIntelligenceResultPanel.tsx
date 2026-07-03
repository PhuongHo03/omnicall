import { useCallback, useMemo, useState } from "react";
import {
  BookOpen,
  Brain,
  Calendar,
  CheckCircle2,
  ChevronRight,
  FileText,
  MessageSquareQuote,
  Minus,
  ShieldQuestion,
  Users,
  XCircle,
} from "lucide-react";

import type { MeetingIntelligenceResult } from "../types/meetingTypes";

type MeetingIntelligenceResultPanelProps = {
  result: MeetingIntelligenceResult;
};

type SectionMeta = {
  icon: typeof BookOpen;
  label: string;
};

const SECTION_META: Record<string, SectionMeta> = {
  meeting: { icon: Calendar, label: "Meeting" },
  source: { icon: FileText, label: "Source" },
  participants: { icon: Users, label: "Participants" },
  summary: { icon: BookOpen, label: "Summary" },
  analysis: { icon: Brain, label: "Analysis" },
  transcript: { icon: MessageSquareQuote, label: "Transcript" },
  citations: { icon: ShieldQuestion, label: "Citations" },
  quality: { icon: CheckCircle2, label: "Quality" },
};

const SECTION_ORDER = ["meeting", "source", "participants", "summary", "analysis", "transcript", "citations", "quality"];
const DEFAULT_OPEN_SECTIONS = new Set<string>();
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

function JsonSection({
  isOpen,
  onToggle,
  sectionKey,
  value
}: {
  isOpen: boolean;
  onToggle: (isOpen: boolean) => void;
  sectionKey: string;
  value: unknown;
}) {
  const meta = SECTION_META[sectionKey] ?? { icon: FileText, label: labelize(sectionKey) };
  const Icon = meta.icon;
  const count = getArrayOrObjectCount(value);

  return (
    <section className="json-section">
      <button
        aria-expanded={isOpen}
        className="json-section__toggle"
        type="button"
        onClick={() => onToggle(!isOpen)}
      >
        <span className="json-section__toggle-left">
          <Icon size={15} className="json-section__icon" />
          <span className="json-section__title">{meta.label}</span>
          {count !== null && <span className="json-section__badge">{count}</span>}
        </span>
        <ChevronRight size={14} className={`json-section__chevron${isOpen ? " json-section__chevron--open" : ""}`} />
      </button>
      {isOpen ? (
        <div className="json-section__body">
          <JsonValue value={value} depth={0} />
        </div>
      ) : null}
    </section>
  );
}

function JsonValue({ value, depth }: { value: unknown; depth: number }) {
  if (value === null || value === undefined) {
    return <span className="json-null">null</span>;
  }
  if (typeof value === "boolean") {
    return value
      ? <span className="json-bool json-bool--true"><CheckCircle2 size={12} /> Yes</span>
      : <span className="json-bool json-bool--false"><XCircle size={12} /> No</span>;
  }
  if (typeof value === "number") {
    return <span className="json-number">{formatNumber(value)}</span>;
  }
  if (typeof value === "string") {
    return <JsonString value={value} />;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="json-empty">Empty</span>;
    }
    // Array of primitives
    if (value.every((item) => typeof item !== "object" || item === null)) {
      return (
        <div className="json-tag-list">
          {value.map((item, index) => (
            <span key={index} className="json-tag">{String(item)}</span>
          ))}
        </div>
      );
    }
    // Array of objects — render as cards
    return (
      <div className="json-card-list">
        {value.map((item, index) => (
          <div key={index} className="json-card">
            <JsonValue value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }
  if (isRecord(value)) {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return <span className="json-empty">Empty</span>;
    }
    return (
      <dl className={depth > 0 ? "json-map json-map--nested" : "json-map"}>
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

function JsonString({ value }: { value: string }) {
  // Detect timestamps like "00:01:15" or long text
  const isLongText = value.length > 120 || value.includes("\n");
  if (isLongText) {
    return <span className="json-text-block">{value}</span>;
  }
  return <span className="json-string">{value}</span>;
}

// ── Helpers ──

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function formatNumber(value: number): string {
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toFixed(2);
}

function getArrayOrObjectCount(value: unknown): number | null {
  if (Array.isArray(value)) return value.length;
  if (isRecord(value)) {
    const keys = Object.keys(value);
    return keys.length > 0 ? keys.length : null;
  }
  return null;
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
    // silent
  }
}

function isBooleanRecord(value: unknown): value is Record<string, boolean> {
  if (!isRecord(value)) return false;
  return Object.values(value).every((entry) => typeof entry === "boolean");
}

function labelize(value: string) {
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

// Remove unused import
void Minus;
