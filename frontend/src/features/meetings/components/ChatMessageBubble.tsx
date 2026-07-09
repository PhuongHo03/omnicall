import { useEffect, useRef, useState } from "react";

import { useAutoScroll } from "../hooks/useAutoScroll";
import { useFormattedTypewriter } from "../hooks/useFormattedTypewriter";
import type { MeetingChatCitation, MeetingChatMessage } from "../types/meetingTypes";
import { formatCitationKind, formatSectionType } from "../utils/citationFormatters";

type ChatMessageBubbleProps = {
  enableTypewriter: boolean;
  message: MeetingChatMessage;
  onTypewriterComplete: (id: string) => void;
  threadRef: React.RefObject<HTMLDivElement | null>;
};

export function ChatMessageBubble({
  enableTypewriter,
  message,
  onTypewriterComplete,
  threadRef,
}: ChatMessageBubbleProps) {
  const evidenceState = typeof message.metadata.evidenceState === "string" ? message.metadata.evidenceState : null;
  const isStreaming = message.metadata.streaming === true;
  const isTyping = message.metadata.pending === true && !isStreaming;
  const agentMetadata = message.agentMetadata;
  const content = typeof message.content === "string" ? message.content : "";

  const { displayed, visibleHtml, isAnimating } = useFormattedTypewriter(
    content,
    enableTypewriter && !isTyping && message.role === "assistant",
  );

  useAutoScroll(threadRef, [isAnimating, displayed]);

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
      {agentMetadata?.toolCalls && agentMetadata.toolCalls.length > 0 ? (
        <div className="agent-tools">
          <span className="agent-tools__label">Tools:</span>
          {agentMetadata.toolCalls.map((tool, index) => (
            <span key={index} className="agent-tool-badge">{tool}</span>
          ))}
        </div>
      ) : null}
      {isTyping ? (
        <p>{content}<span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" /></p>
      ) : isAnimating ? (
        <div className="chat-message__body"><span dangerouslySetInnerHTML={{ __html: (isAnimating ? visibleHtml : displayed) + '<span class="chat-caret"></span>' }} /></div>
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
