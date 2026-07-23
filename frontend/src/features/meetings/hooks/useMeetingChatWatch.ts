import { useCallback, useRef, type Dispatch, type RefObject, type SetStateAction } from "react";

import { getMeetingChatHistory } from "../api/meetingApi";
import { streamChatEvents, type ChatStreamEvent } from "../api/chatStreamApi";
import { appendLivePipelineStage, completedAssistantMessageIds } from "../states/chatState";
import type { MeetingChatMessage } from "../types/meetingTypes";

type UseMeetingChatWatchArgs = {
  applyChatHistory: (messages: MeetingChatMessage[]) => void;
  token: string;
  currentMeetingIdRef: RefObject<string | null>;
  setChatMessages: Dispatch<SetStateAction<MeetingChatMessage[]>>;
  setTypewriterMessageIds: Dispatch<SetStateAction<Set<string>>>;
};

const MAX_RECONNECT = 3;
const RECONNECT_DELAY_MS = 2000;
const POLL_INTERVAL_MS = 3000;

export function useMeetingChatWatch({
  applyChatHistory,
  currentMeetingIdRef,
  setChatMessages,
  setTypewriterMessageIds,
  token,
}: UseMeetingChatWatchArgs) {
  const chatPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sseCloseRef = useRef<(() => void) | null>(null);

  const addCompletedAssistantTypewriterIds = useCallback(
    (messages: MeetingChatMessage[]) => {
      const newAssistantIds = completedAssistantMessageIds(messages);
      if (newAssistantIds.length > 0) {
        setTypewriterMessageIds((prev) => {
          const next = new Set(prev);
          newAssistantIds.forEach((id) => next.add(id));
          return next;
        });
      }
    },
    [setTypewriterMessageIds]
  );

  const stopChatWatch = useCallback(() => {
    if (sseCloseRef.current) {
      sseCloseRef.current();
      sseCloseRef.current = null;
    }
    if (chatPollingRef.current) {
      clearInterval(chatPollingRef.current);
      chatPollingRef.current = null;
    }
  }, []);

  const startChatWatch = useCallback(
    (meetingId: string, options?: { turnId?: string; statusMessageId?: string }) => {
      const statusMessageId = options?.statusMessageId ?? null;
      const turnId = options?.turnId;
      let reconnectAttempts = 0;

      stopChatWatch();

      const loadCompletedHistory = () => {
        void getMeetingChatHistory(token, meetingId).then((history) => {
          applyChatHistory(history.messages);
          addCompletedAssistantTypewriterIds(history.messages);
        }).catch(() => {
          // The terminal SSE payload already contains the persisted assistant
          // message; a later poll can reconcile a transient history failure.
        });
      };

      const applyPersistedAssistant = (persisted: MeetingChatMessage | undefined): boolean => {
        if (!persisted || persisted.role !== "assistant") return false;
        setChatMessages((current) => [
          ...current.filter((item) => item.id !== persisted.id && item.id !== statusMessageId),
          persisted,
        ]);
        setTypewriterMessageIds((current) => new Set(current).add(persisted.id));
        return true;
      };

      const finishTerminalEvent = (
        event: Extract<ChatStreamEvent, { type: "done" | "blocked" | "clarification" | "clarification_needed" }>,
      ) => {
        const hasPersistedMessage = applyPersistedAssistant(event.assistantMessage);
        if (!hasPersistedMessage && statusMessageId) {
          const content = event.type === "done" ? event.answer : event.message;
          setChatMessages((current) => current.map((item) => item.id === statusMessageId
            ? {
                ...item,
                content,
                metadata: {
                  ...item.metadata,
                  ...(event.type === "clarification" || event.type === "clarification_needed"
                    ? { clarificationNeeded: true, evidenceState: "clarification_needed" as const }
                    : {}),
                  pending: false,
                  streaming: false,
                },
              }
            : item));
        }
        stopChatWatch();
        loadCompletedHistory();
      };

      const connectSse = () => {
        if (currentMeetingIdRef.current !== meetingId) return;

        const closeSse = streamChatEvents(token, meetingId, turnId, (event: ChatStreamEvent) => {
          if (currentMeetingIdRef.current !== meetingId) return;
          if (turnId && event.type !== "connected" && event.type !== "token" && event.turnId !== turnId) return;
          reconnectAttempts = 0;
          if (event.type === "status" && statusMessageId) {
            setChatMessages((current) =>
              current.map((item) => item.id === statusMessageId
                ? {
                    ...item,
                    content: event.message,
                    metadata: event.stage === "clarification_needed"
                      ? { ...item.metadata, clarificationNeeded: true, evidenceState: "clarification_needed" }
                      : { ...item.metadata, pipelineTrace: appendLivePipelineStage(item.metadata.pipelineTrace, event.stage) },
                  }
                : item)
            );
          } else if (event.type === "clarification" || event.type === "clarification_needed") {
            finishTerminalEvent(event);
          } else if (event.type === "done" || event.type === "blocked") {
            finishTerminalEvent(event);
          } else if (event.type === "error" && statusMessageId) {
            setChatMessages((current) => current.map((item) => item.id === statusMessageId
              ? { ...item, content: event.message, metadata: { ...item.metadata, pending: false, streaming: false, evidenceState: "error" as const } }
              : item));
            stopChatWatch();
            loadCompletedHistory();
          }
        }, undefined, () => {
          sseCloseRef.current = null;
          if (currentMeetingIdRef.current !== meetingId) return;
          if (chatPollingRef.current && reconnectAttempts < MAX_RECONNECT) {
            reconnectAttempts += 1;
            setTimeout(connectSse, RECONNECT_DELAY_MS);
          }
        });
        sseCloseRef.current = closeSse;
      };

      connectSse();

      chatPollingRef.current = setInterval(() => {
        if (currentMeetingIdRef.current !== meetingId) {
          stopChatWatch();
          return;
        }
        void getMeetingChatHistory(token, meetingId).then((history) => {
          const lastMsg = history.messages[history.messages.length - 1];
          if (lastMsg && lastMsg.role === "assistant" && !lastMsg.metadata.pending) {
            stopChatWatch();
            applyChatHistory(history.messages);
            addCompletedAssistantTypewriterIds(history.messages);
          }
        }).catch(() => {
          // Keep watching; transient history failures must not discard SSE state.
        });
      }, POLL_INTERVAL_MS);
    },
    [
      addCompletedAssistantTypewriterIds,
      applyChatHistory,
      currentMeetingIdRef,
      setChatMessages,
      stopChatWatch,
      token,
    ]
  );

  return {
    startChatWatch,
    stopChatWatch,
  };
}
