import { Braces, Clock3, Cpu, FileAudio, MessageSquareText, Workflow } from "lucide-react";
import { EmptyState } from "../../../shared/components/EmptyState";

import type { AdminOperationalLog } from "../types/adminTypes";
import { adminLogProvenanceRows } from "./adminLogProvenance";

type AdminLogDetailsProps = {
  event: AdminOperationalLog | null;
  meetingNames?: Map<string, string>;
};

export function AdminLogDetails({ event, meetingNames }: AdminLogDetailsProps) {
  if (!event) {
    return <div className="admin-log-details admin-log-details--empty"><EmptyState message="Select an event to inspect its metadata." /></div>;
  }

  const resolvedMeetingName = event.meetingId && meetingNames ? meetingNames.get(event.meetingId) ?? event.meetingName : event.meetingName;
  const question = stringValue(event.chat.question) ?? stringValue(event.chat.questionPreview);
  const answer = stringValue(event.chat.answer);

  const rows = [
    ["Meeting Name", resolvedMeetingName],
    ["Meeting ID", event.meetingId],
    ["File", stringValue(event.file.name)],
    ["File ID", stringValue(event.file.id)],
    ["Chat turn", stringValue(event.chat.turnId)],
    ["User message", stringValue(event.chat.userMessageId)],
    ["Assistant message", stringValue(event.chat.assistantMessageId)],
    ...adminLogProvenanceRows(event),
    ["Duration", event.durationMs === null ? null : `${event.durationMs} ms`],
    ["Status", event.status]
  ].filter((row): row is [string, string] => typeof row[1] === "string" && Boolean(row[1]));

  return (
    <aside className="admin-log-details">
      <div className="admin-log-details__header">
        <div className={`admin-log-details__icon admin-log-details__icon--${event.level}`}>
          {event.flow === "rag" ? <MessageSquareText size={18} /> : <Workflow size={18} />}
        </div>
        <div>
          <span>{event.flow === "rag" ? "RAG Chat Event" : "Processing Event"}</span>
          <h2>{event.message}</h2>
        </div>
      </div>

      <div className="admin-log-details__meta">
        <span>
          <Clock3 size={14} />
          {new Date(event.timestamp).toLocaleString()}
        </span>
        <span>
          <Cpu size={14} />
          {event.stage}
        </span>
        {stringValue(event.file.name) ? (
          <span>
            <FileAudio size={14} />
            {stringValue(event.file.name)}
          </span>
        ) : null}
      </div>

      <dl className="admin-log-details__grid">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      {question || answer ? (
        <section className="admin-log-conversation" aria-label="Chat content">
          {question ? (
            <div>
              <strong>Question</strong>
              <p>{question}</p>
            </div>
          ) : null}
          {answer ? (
            <div>
              <strong>Answer</strong>
              <p>{answer}</p>
            </div>
          ) : null}
        </section>
      ) : null}

      {event.errorMessage ? (
        <div className="admin-log-details__error">
          <strong>{event.errorType ?? "Error"}</strong>
          <p>{event.errorMessage}</p>
        </div>
      ) : null}

      <div className="admin-log-json">
        <div>
          <Braces size={15} />
          <strong>Event metadata</strong>
        </div>
        <pre>{JSON.stringify({
          provenance: {
            executorType: event.executorType,
            provider: event.effectiveProvider ?? event.provider,
            model: event.effectiveModel ?? event.model,
            answerProvider: event.executorType === "cache" && event.details.served === true
              ? event.originProvider
              : null,
            answerModel: event.executorType === "cache" && event.details.served === true
              ? event.originModel
              : null,
            resource: event.resource,
            operation: event.operation,
            version: event.version,
            fallbackUsed: event.fallbackUsed
          },
          file: event.file,
          chat: traceChatMetadata(event.chat),
          details: event.details
        }, null, 2)}</pre>
      </div>
    </aside>
  );
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function traceChatMetadata(chat: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(chat).filter(([key]) => key !== "question" && key !== "answer")
  );
}
