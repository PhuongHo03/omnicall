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
  Network,
  Sparkles,
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
  evidence: { icon: ShieldQuestion, label: "Evidence" },
  speakers: { icon: MessageSquareQuote, label: "Speakers" },
  participants: { icon: Users, label: "Participants" },
  entities: { icon: Brain, label: "Entities" },
  facts: { icon: CheckCircle2, label: "Facts" },
  events: { icon: Calendar, label: "Events" },
  relationships: { icon: Network, label: "Relationships" },
  topics: { icon: BookOpen, label: "Topics" },
  summaries: { icon: BookOpen, label: "Summaries" },
  actions: { icon: CheckCircle2, label: "Actions" },
  decisions: { icon: CheckCircle2, label: "Decisions" },
  risks: { icon: ShieldQuestion, label: "Risks" },
  questions: { icon: MessageSquareQuote, label: "Questions" },
  transcript: { icon: MessageSquareQuote, label: "Transcript" },
  quality: { icon: CheckCircle2, label: "Quality" },
  extraction: { icon: Sparkles, label: "Extraction" },
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
