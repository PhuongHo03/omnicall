import { useCallback, useRef, type Dispatch, type RefObject, type SetStateAction } from "react";

import { getMeetingChatHistory } from "../api/meetingApi";
import { streamChatEvents, type ChatStreamEvent } from "../api/chatStreamApi";
import { completedAssistantMessageIds, formatAgentSearchMessage } from "../states/chatState";
import type { MeetingChatMessage } from "../types/meetingTypes";

type UseMeetingChatWatchArgs = {
  token: string;
  currentMeetingIdRef: RefObject<string | null>;
  setChatMessages: Dispatch<SetStateAction<MeetingChatMessage[]>>;
  setTypewriterMessageIds: Dispatch<SetStateAction<Set<string>>>;
};

const MAX_RECONNECT = 3;
const RECONNECT_DELAY_MS = 2000;
const POLL_INTERVAL_MS = 3000;

export function useMeetingChatWatch({
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
    (meetingId: string, options?: { statusMessageId?: string }) => {
      const statusMessageId = options?.statusMessageId ?? null;
      let reconnectAttempts = 0;

      stopChatWatch();

      const loadCompletedHistory = () => {
        void getMeetingChatHistory(token, meetingId).then((history) => {
          setChatMessages(history.messages);
          addCompletedAssistantTypewriterIds(history.messages);
        });
      };

      const connectSse = () => {
        if (currentMeetingIdRef.current !== meetingId) return;

        const closeSse = streamChatEvents(token, meetingId, (event: ChatStreamEvent) => {
          if (currentMeetingIdRef.current !== meetingId) return;
          reconnectAttempts = 0;
          if (event.type === "status" && statusMessageId) {
            setChatMessages((current) =>
              current.map((item) => item.id === statusMessageId ? { ...item, content: event.message } : item)
            );
          } else if (event.type === "agent_think" && statusMessageId) {
            setChatMessages((current) =>
              current.map((item) =>
                item.id === statusMessageId
                  ? {
                      ...item,
                      content: event.message,
                      agentMetadata: {
                        ...item.agentMetadata,
                        iterations: event.iteration,
                        agentThoughts: [
                          ...(item.agentMetadata?.agentThoughts ?? []),
                          event.message,
                        ],
                      },
                    }
                  : item
              )
            );
          } else if (event.type === "agent_search" && statusMessageId) {
            const tools = Array.isArray(event.tools) ? event.tools : [];
            const message = event.message ?? formatAgentSearchMessage(tools);
            setChatMessages((current) =>
              current.map((item) =>
                item.id === statusMessageId
                  ? {
                      ...item,
                      content: message,
                      agentMetadata: {
                        ...item.agentMetadata,
                        iterations: event.iteration,
                        toolCalls: tools,
                      },
                    }
                  : item
              )
            );
          } else if (event.type === "observation" && statusMessageId) {
            const resultCount = event.total_chunks ?? event.resultCount ?? 0;
            setChatMessages((current) =>
              current.map((item) =>
                item.id === statusMessageId
                  ? { ...item, content: `Đã tìm thấy ${resultCount} đoạn liên quan` }
                  : item
              )
            );
          } else if (event.type === "agent_synthesize" && statusMessageId) {
            const message = event.message ?? "Đang tạo câu trả lời cuối cùng...";
            setChatMessages((current) =>
              current.map((item) => item.id === statusMessageId ? { ...item, content: message } : item)
            );
          } else if (event.type === "fast_path" && statusMessageId) {
            setChatMessages((current) =>
              current.map((item) =>
                item.id === statusMessageId
                  ? {
                      ...item,
                      content: event.message,
                      metadata: { ...item.metadata, intent: event.intent ?? "fast_path" },
                    }
                  : item
              )
            );
          } else if (event.type === "done" || event.type === "blocked") {
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
            setChatMessages(history.messages);
            addCompletedAssistantTypewriterIds(history.messages);
          }
        });
      }, POLL_INTERVAL_MS);
    },
    [
      addCompletedAssistantTypewriterIds,
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
