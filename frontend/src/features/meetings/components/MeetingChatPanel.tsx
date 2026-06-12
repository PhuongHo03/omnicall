import { MessageSquare, RefreshCw, Send } from "lucide-react";

import { IconButton } from "../../../components/IconButton";
import type { Meeting, MeetingChatCitation, MeetingChatMessage } from "../types/meetingTypes";

type MeetingChatPanelProps = {
  disabled: boolean;
  messages: MeetingChatMessage[];
  question: string;
  selectedMeeting: Meeting | null;
  sessionId: string | null;
  onQuestionChange: (question: string) => void;
  onRefreshHistory: () => void;
  onSubmitQuestion: () => void;
};

export function MeetingChatPanel({
  disabled,
  messages,
  onQuestionChange,
  onRefreshHistory,
  onSubmitQuestion,
  question,
  selectedMeeting,
  sessionId
}: MeetingChatPanelProps) {
  const canChat = Boolean(selectedMeeting) && selectedMeeting?.status === "READY" && !disabled;
  const hasSession = Boolean(sessionId);

  return (
    <section className="detail-panel chat-panel">
      <div className="detail-header chat-panel__header">
        <div>
          <h2>Meeting chat</h2>
          <span>{selectedMeeting?.status === "READY" ? selectedMeeting.id : "Waiting for a ready meeting"}</span>
        </div>
        <IconButton
          icon={<RefreshCw size={16} />}
          label="Refresh"
          disabled={!canChat || !hasSession}
          onClick={onRefreshHistory}
          variant="secondary"
        />
      </div>

      <div className="chat-thread" aria-live="polite">
        {messages.length === 0 ? (
          <div className="empty-panel">No chat messages yet.</div>
        ) : (
          messages.map((message) => <ChatMessageBubble key={message.id} message={message} />)
        )}
      </div>

      <form
        className="chat-composer"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmitQuestion();
        }}
      >
        <label>
          <span>Question</span>
          <textarea
            value={question}
            disabled={!canChat}
            maxLength={2000}
            rows={3}
            onChange={(event) => onQuestionChange(event.target.value)}
          />
        </label>
        <IconButton
          type="submit"
          icon={canChat ? <Send size={16} /> : <MessageSquare size={16} />}
          label="Ask"
          disabled={!canChat || !question.trim()}
          variant="primary"
        />
      </form>
    </section>
  );
}

function ChatMessageBubble({ message }: { message: MeetingChatMessage }) {
  const evidenceState = typeof message.metadata.evidenceState === "string" ? message.metadata.evidenceState : null;

  return (
    <article className={`chat-message chat-message--${message.role}`}>
      <div className="chat-message__meta">
        <strong>{message.role === "assistant" ? "Assistant" : "You"}</strong>
        {evidenceState ? <span className={`evidence-badge evidence-badge--${evidenceState}`}>{evidenceState}</span> : null}
      </div>
      <p>{message.content}</p>
      {message.citations.length > 0 ? (
        <div className="citation-list">
          {message.citations.map((citation) => (
            <CitationCard key={`${message.id}-${citation.chunkId}`} citation={citation} />
          ))}
        </div>
      ) : null}
    </article>
  );
}

function CitationCard({ citation }: { citation: MeetingChatCitation }) {
  return (
    <div className="citation-card">
      <div className="citation-card__topline">
        <strong>{citation.sectionType}</strong>
        <span>{formatRange(citation.startMs, citation.endMs)}</span>
      </div>
      <span>{citation.jsonPointer}</span>
      <p>{citation.text}</p>
    </div>
  );
}

function formatRange(startMs: number | null, endMs: number | null) {
  if (startMs === null && endMs === null) {
    return "section";
  }
  return `${formatMs(startMs)}-${formatMs(endMs)}`;
}

function formatMs(value: number | null) {
  if (value === null || value < 0) {
    return "?";
  }
  const totalSeconds = Math.floor(value / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
