import { useEffect, useRef, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";

import { useAutoScroll } from "../hooks/useAutoScroll";
import { useFormattedTypewriter } from "../hooks/useFormattedTypewriter";
import { isFeedbackEligibleMessage, toggledFeedbackSelection } from "../states/chatState";
import type { ChatFeedbackSelection, MeetingChatCitation, MeetingChatMessage } from "../types/meetingTypes";
import { formatCitationKind, formatRange, formatSectionType } from "../utils/citationFormatters";
import { PipelineTraceViewer } from "./PipelineTraceViewer";

type ChatMessageBubbleProps = {
  enableTypewriter: boolean;
  message: MeetingChatMessage;
  onTypewriterComplete: (id: string) => void;
  threadRef: React.RefObject<HTMLDivElement | null>;
  onCitationClick: (citation: MeetingChatCitation) => void;
  onFeedback: (messageId: string, rating: ChatFeedbackSelection) => void;
  feedbackPending: boolean;
};

export function ChatMessageBubble({
  enableTypewriter,
  message,
  onTypewriterComplete,
  threadRef,
  onCitationClick,
  onFeedback,
  feedbackPending,
}: ChatMessageBubbleProps) {
  const [openInsight, setOpenInsight] = useState<"flow" | "citations" | null>(null);
  const evidenceState = typeof message.metadata.evidenceState === "string" ? message.metadata.evidenceState : null;
  const isStreaming = message.metadata.streaming === true;
  const isTyping = message.metadata.pending === true && !isStreaming;
  const content = typeof message.content === "string" ? message.content : "";
  const feedbackRating = message.feedbackRating;
  const feedbackEligible = isFeedbackEligibleMessage(message);

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
      {isTyping ? (
        <p>{content}<span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" /></p>
      ) : isAnimating ? (
        <div className="chat-message__body"><span dangerouslySetInnerHTML={{ __html: (isAnimating ? visibleHtml : displayed) + '<span class="chat-caret"></span>' }} /></div>
      ) : (
        <div className="chat-message__body" dangerouslySetInnerHTML={{ __html: displayed }} />
      )}
      {message.role === "assistant" ? (
        <div className="chat-message__insights">
          <PipelineTraceViewer
            isOpen={openInsight === "flow"}
            message={message}
            onToggle={() => setOpenInsight((current) => current === "flow" ? null : "flow")}
          />
          {message.citations.length > 0 ? (
            <CitationsBadge
              citations={message.citations}
              isOpen={openInsight === "citations"}
              messageId={message.id}
              onCitationClick={onCitationClick}
              onToggle={() => setOpenInsight((current) => current === "citations" ? null : "citations")}
            />
          ) : null}
        </div>
      ) : null}
      {feedbackEligible ? (
        <div className="chat-feedback" aria-label="Answer feedback" aria-busy={feedbackPending}>
          <button
            type="button"
            className={feedbackRating === "up" ? "chat-feedback__button chat-feedback__button--selected" : "chat-feedback__button"}
            onClick={() => onFeedback(message.id, toggledFeedbackSelection(feedbackRating, "up"))}
            aria-label={feedbackRating === "up" ? "Remove helpful feedback" : "Helpful answer"}
            aria-pressed={feedbackRating === "up"}
            disabled={feedbackPending}
          >
            <ThumbsUp size={14} />
          </button>
          <button
            type="button"
            className={feedbackRating === "down" ? "chat-feedback__button chat-feedback__button--selected" : "chat-feedback__button"}
            onClick={() => onFeedback(message.id, toggledFeedbackSelection(feedbackRating, "down"))}
            aria-label={feedbackRating === "down" ? "Remove unhelpful feedback" : "Unhelpful answer"}
            aria-pressed={feedbackRating === "down"}
            disabled={feedbackPending}
          >
            <ThumbsDown size={14} />
          </button>
        </div>
      ) : null}
    </article>
  );
}

function CitationsBadge({
  citations,
  isOpen,
  messageId,
  onCitationClick,
  onToggle,
}: {
  citations: MeetingChatCitation[];
  isOpen: boolean;
  messageId: string;
  onCitationClick: (citation: MeetingChatCitation) => void;
  onToggle: () => void;
}) {
  const sourcesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen && sourcesRef.current) {
      const bubble = sourcesRef.current.closest(".chat-message");
      bubble?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [isOpen]);

  return (
    <div className="sources" ref={sourcesRef}>
      <button aria-expanded={isOpen} className="sources__badge" type="button" onClick={onToggle}>
        <span>Citations ({citations.length})</span>
        <span className={"sources__chevron" + (isOpen ? " sources__chevron--open" : "")}>&#9662;</span>
      </button>
      {isOpen ? (
        <div className="sources__list">
          {citations.map((citation) => (
            <CitationCard key={messageId + "-" + citation.citationId} citation={citation} onCitationClick={onCitationClick} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function CitationCard({ citation, onCitationClick }: { citation: MeetingChatCitation; onCitationClick: (citation: MeetingChatCitation) => void }) {
  const canSeek = citation.startMs !== null || citation.segmentIds.length > 0;
  return (
    <div className="citation-card">
      <div className="citation-card__topline">
        <strong>{formatSectionType(citation.sectionType)}</strong>
        <span>{formatCitationKind(citation)}</span>
      </div>
      <span>{citation.jsonPointer}</span>
      <p>{citation.quote}</p>
      {canSeek ? (
        <button className="citation-card__playback" type="button" onClick={() => onCitationClick(citation)}>
          Play citation{citation.startMs !== null ? ` from ${formatRange(citation.startMs, citation.endMs)}` : ""}
        </button>
      ) : null}
    </div>
  );
}
