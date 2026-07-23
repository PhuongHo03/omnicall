import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { setChatFeedback } from "../api/meetingApi";
import { isFeedbackEligibleMessage, mergeChatHistory } from "../states/chatState";
import type {
  ChatFeedbackSelection,
  MeetingChatMessage,
} from "../types/meetingTypes";

type UseChatFeedbackArgs = {
  meetingId: string | null;
  messages: MeetingChatMessage[];
  onError: (message: string) => void;
  setMessages: Dispatch<SetStateAction<MeetingChatMessage[]>>;
  token: string;
};

type FeedbackSnapshot = Pick<
  MeetingChatMessage,
  "feedbackRating" | "feedbackRevision" | "feedbackStatus" | "feedbackCacheAction"
>;

export function useChatFeedback({
  meetingId,
  messages,
  onError,
  setMessages,
  token,
}: UseChatFeedbackArgs) {
  const messagesRef = useRef(messages);
  const pendingMessageIdsRef = useRef(new Set<string>());
  const requestVersionsRef = useRef(new Map<string, number>());
  const scopeVersionRef = useRef(0);
  const [pendingMessageIds, setPendingMessageIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    scopeVersionRef.current += 1;
    pendingMessageIdsRef.current.clear();
    requestVersionsRef.current.clear();
    setPendingMessageIds(new Set());
  }, [meetingId, token]);

  const updateMessages = useCallback((
    updater: (current: MeetingChatMessage[]) => MeetingChatMessage[],
  ) => {
    setMessages((current) => {
      const next = updater(current);
      messagesRef.current = next;
      return next;
    });
  }, [setMessages]);

  const submitChatFeedback = useCallback((messageId: string, rating: ChatFeedbackSelection) => {
    if (!meetingId || pendingMessageIdsRef.current.has(messageId)) return;
    const message = messagesRef.current.find((item) => item.id === messageId);
    if (!message || !isFeedbackEligibleMessage(message)) return;

    const previous: FeedbackSnapshot = {
      feedbackRating: message.feedbackRating,
      feedbackRevision: message.feedbackRevision,
      feedbackStatus: message.feedbackStatus,
      feedbackCacheAction: message.feedbackCacheAction,
    };
    const requestVersion = (requestVersionsRef.current.get(messageId) ?? 0) + 1;
    const scopeVersion = scopeVersionRef.current;
    requestVersionsRef.current.set(messageId, requestVersion);
    pendingMessageIdsRef.current.add(messageId);
    setPendingMessageIds((current) => new Set(current).add(messageId));
    updateMessages((current) => current.map((item) => item.id === messageId
      ? {
          ...item,
          feedbackRating: rating === "neutral" ? null : rating,
          feedbackStatus: "pending",
        }
      : item));

    void setChatFeedback(token, meetingId, messageId, rating, previous.feedbackRevision)
      .then((result) => {
        if (
          scopeVersionRef.current !== scopeVersion
          || requestVersionsRef.current.get(messageId) !== requestVersion
        ) {
          return;
        }
        updateMessages((current) => current.map((item) => item.id === messageId
          ? {
              ...item,
              feedbackRating: result.rating === "neutral" ? null : result.rating,
              feedbackRevision: result.revision,
              feedbackStatus: result.status,
              feedbackCacheAction: result.cacheAction,
            }
          : item));
      })
      .catch((caught: unknown) => {
        if (
          scopeVersionRef.current !== scopeVersion
          || requestVersionsRef.current.get(messageId) !== requestVersion
        ) {
          return;
        }
        updateMessages((current) => current.map((item) => {
          if (item.id !== messageId) return item;
          return item.feedbackRevision > previous.feedbackRevision
            ? item
            : { ...item, ...previous };
        }));
        onError(caught instanceof Error ? caught.message : "Could not save answer feedback.");
      })
      .finally(() => {
        if (
          scopeVersionRef.current !== scopeVersion
          || requestVersionsRef.current.get(messageId) !== requestVersion
        ) {
          return;
        }
        pendingMessageIdsRef.current.delete(messageId);
        setPendingMessageIds((current) => {
          const next = new Set(current);
          next.delete(messageId);
          return next;
        });
      });
  }, [meetingId, onError, token, updateMessages]);

  const applyChatHistory = useCallback((incoming: MeetingChatMessage[]) => {
    updateMessages((current) => mergeChatHistory(
      current,
      incoming,
      pendingMessageIdsRef.current,
    ));
  }, [updateMessages]);

  return {
    applyChatHistory,
    pendingFeedbackMessageIds: pendingMessageIds,
    submitChatFeedback,
  };
}
