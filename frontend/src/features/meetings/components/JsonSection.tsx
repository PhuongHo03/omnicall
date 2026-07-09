import {
  BookOpen,
  Brain,
  Calendar,
  CheckCircle2,
  ChevronRight,
  FileText,
  MessageSquareQuote,
  ShieldQuestion,
  Users,
} from "lucide-react";

import { getArrayOrObjectCount, labelize } from "../utils/jsonDisplay";
import { JsonValue } from "./JsonValue";

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

export function JsonSection({
  isOpen,
  onToggle,
  sectionKey,
  value,
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
