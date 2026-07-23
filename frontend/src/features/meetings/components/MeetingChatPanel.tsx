import { Send } from "lucide-react";
import { EmptyState } from "../../../shared/components/EmptyState";
import { useEffect, useRef } from "react";

import { useAutoScroll } from "../hooks/useAutoScroll";
import type { ChatFeedbackSelection, MeetingChatCitation, MeetingChatMessage } from "../types/meetingTypes";
import { ChatMessageBubble } from "./ChatMessageBubble";

type MeetingChatPanelProps = {
  disabled: boolean;
  messages: MeetingChatMessage[];
  question: string;
  onQuestionChange: (question: string) => void;
  onSubmitQuestion: () => void;
  typewriterMessageIds: Set<string>;
  onTypewriterComplete: (id: string) => void;
  onCitationClick: (citation: MeetingChatCitation) => void;
  onFeedback: (messageId: string, rating: ChatFeedbackSelection) => void;
  pendingFeedbackMessageIds: ReadonlySet<string>;
};

export function MeetingChatPanel({
  disabled,
  messages,
  onQuestionChange,
  onSubmitQuestion,
  question,
  typewriterMessageIds,
  onTypewriterComplete,
  onCitationClick,
  onFeedback,
  pendingFeedbackMessageIds,
}: MeetingChatPanelProps) {
  const isWaitingForAnswer = messages.length > 0 && Boolean(messages[messages.length - 1].metadata?.pending);
  const canChat = !disabled && !isWaitingForAnswer;
  const threadRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // Auto-scroll when new messages arrive
  useAutoScroll(threadRef, [messages.length]);

  // Auto-focus input when canChat becomes available
  useEffect(() => {
    if (canChat && inputRef.current) {
      inputRef.current.focus();
    }
  }, [canChat]);

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
            {messages.map((message) => <ChatMessageBubble key={message.id} message={message} enableTypewriter={typewriterMessageIds.has(message.id)} onTypewriterComplete={onTypewriterComplete} threadRef={threadRef} onCitationClick={onCitationClick} onFeedback={onFeedback} feedbackPending={pendingFeedbackMessageIds.has(message.id)} />)}
          </>
        )}
      </div>

      <form
        className="chat-composer"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <div className="chat-composer__wrap">
          <textarea
            ref={inputRef}
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
            type="button"
            disabled={!canChat || !question.trim()}
            aria-label="Ask"
            onClick={() => onSubmitQuestion()}
          >
            <Send size={15} />
          </button>
        </div>
      </form>
    </section>
  );
}
