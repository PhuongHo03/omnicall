import { Send } from "lucide-react";
import { EmptyState } from "../../../shared/components/EmptyState";
import { useEffect, useRef, useState } from "react";

import { useAutoScroll } from "../hooks/useAutoScroll";
import { useFormattedTypewriter } from "../hooks/useFormattedTypewriter";
import type { MeetingChatCitation, MeetingChatMessage } from "../types/meetingTypes";

type MeetingChatPanelProps = {
  disabled: boolean;
  messages: MeetingChatMessage[];
  question: string;
  onQuestionChange: (question: string) => void;
  onSubmitQuestion: () => void;
  typewriterMessageIds: Set<string>;
  onTypewriterComplete: (id: string) => void;
};

export function MeetingChatPanel({
  disabled,
  messages,
  onQuestionChange,
  onSubmitQuestion,
  question,
  typewriterMessageIds,
  onTypewriterComplete,
}: MeetingChatPanelProps) {
  const isWaitingForAnswer = messages.length > 0 && Boolean(messages[messages.length - 1].metadata?.pending);
  const canChat = !isWaitingForAnswer;
  const threadRef = useRef<HTMLDivElement>(null);
  useAutoScroll(threadRef, [messages.length]);

  return (
    <section className="chat-panel">
      <div className="chat-panel__header">
        <h2>Meeting chat</h2>
      </div>

      <div className="chat-thread" ref={threadRef} aria-live="polite">
        {messages.length === 0 ? (
          <EmptyState message="No chat messages yet." />
        ) : (
          <>
            {messages.map((message) => <ChatMessageBubble key={message.id} message={message} enableTypewriter={typewriterMessageIds.has(message.id)} onTypewriterComplete={onTypewriterComplete} threadRef={threadRef} />)}
          </>
        )}
      </div>

      <form
        className="chat-composer"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmitQuestion();
        }}
      >
        <div className="chat-composer__wrap">
          <textarea
            className="chat-composer__input"
            value={question}
            disabled={!canChat}
            maxLength={2000}
            rows={1}
            placeholder={canChat ? "Ask about this meeting\u2026" : "Waiting for response\u2026"}
            onChange={(event) => onQuestionChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSubmitQuestion();
              }
            }}
          />
          <button
            className="chat-composer__send"
            type="submit"
            disabled={!canChat || !question.trim()}
            aria-label="Ask"
          >
            <Send size={15} />
          </button>
        </div>
      </form>
    </section>
  );
}

function ChatMessageBubble({ message, enableTypewriter, onTypewriterComplete, threadRef }: { message: MeetingChatMessage; enableTypewriter: boolean; onTypewriterComplete: (id: string) => void; threadRef: React.RefObject<HTMLDivElement | null> }) {
  const evidenceState = typeof message.metadata.evidenceState === "string" ? message.metadata.evidenceState : null;
  const isStreaming = message.metadata.streaming === true;
  const isTyping = message.metadata.pending === true && !isStreaming;
  const { displayed, isAnimating } = useFormattedTypewriter(
    message.content,
    enableTypewriter && !isTyping && !isStreaming && message.role === "assistant",
  );

  // Auto-scroll during typewriter
  useAutoScroll(threadRef, isAnimating ? [displayed] : []);

  // Complete callback + deferred scroll when typewriter finishes
  useEffect(() => {
    if (enableTypewriter && !isAnimating && message.role === "assistant") {
      onTypewriterComplete(message.id);
      requestAnimationFrame(() => {
        if (threadRef.current) {
          threadRef.current.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
        }
      });
    }
  }, [enableTypewriter, isAnimating, message.id, message.role, onTypewriterComplete, threadRef]);

  return (
    <article className={`chat-message chat-message--${message.role}${isStreaming ? " chat-message--streaming" : ""}${isTyping ? " chat-message--typing" : ""}${isAnimating ? " chat-message--streaming" : ""}`}>
      <div className="chat-message__meta">
        <strong>{message.role === "assistant" ? "Assistant" : "You"}</strong>
        {evidenceState ? <span className={`evidence-badge evidence-badge--${evidenceState}`}>{evidenceState}</span> : null}
      </div>
      {isTyping ? (
        <p>{message.content}<span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" /></p>
      ) : isAnimating ? (
        <div className="chat-message__body"><span dangerouslySetInnerHTML={{ __html: displayed }} /><span className="chat-caret" /></div>
      ) : (
        <div className="chat-message__body" dangerouslySetInnerHTML={{ __html: displayed }} />
      )}
      {message.citations.length > 0 ? (
        <SourcesBadge citations={message.citations} messageId={message.id} />
      ) : null}
    </article>
  );
}

function SourcesBadge({ citations, messageId }: { citations: MeetingChatCitation[]; messageId: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const sourcesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen && sourcesRef.current) {
      const bubble = sourcesRef.current.closest(".chat-message");
      bubble?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [isOpen]);

  return (
    <div className="sources" ref={sourcesRef}>
      <button className="sources__badge" type="button" onClick={() => setIsOpen(!isOpen)}>
        <span>Sources ({citations.length})</span>
        <span className={"sources__chevron" + (isOpen ? " sources__chevron--open" : "")}>&#9662;</span>
      </button>
      {isOpen ? (
        <div className="sources__list">
          {citations.map((citation) => (
            <CitationCard key={messageId + "-" + citation.chunkId} citation={citation} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function CitationCard({ citation }: { citation: MeetingChatCitation }) {
  return (
    <div className="citation-card">
      <div className="citation-card__topline">
        <strong>{formatSectionType(citation.sectionType)}</strong>
        <span>{formatCitationKind(citation)}</span>
      </div>
      <span>{citation.jsonPointer}</span>
      <p>{citation.text}</p>
    </div>
  );
}

function formatSectionType(sectionType: string) {
  return sectionType
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatCitationKind(citation: MeetingChatCitation) {
  const range = formatRange(citation.startMs, citation.endMs);
  if (range !== "section") {
    return range;
  }
  if (citation.sourceType === "metadata") {
    return "metadata";
  }
  if (citation.sourceType === "structured") {
    return "section";
  }
  return citation.sourceType;
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
