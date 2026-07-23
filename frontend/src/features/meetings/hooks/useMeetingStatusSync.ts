import { useCallback, useEffect, useRef, type Dispatch, type RefObject, type SetStateAction } from "react";

import { usePollingEffect } from "../../../shared/hooks/usePollingEffect";
import {
  getMeeting,
  getMeetingChatHistory,
  getMeetingIntelligenceResult,
  listMeetings,
} from "../api/meetingApi";
import { isProcessingMeeting } from "../states/meetingState";
import type {
  Meeting,
  MeetingAsset,
  MeetingChatMessage,
  MeetingIntelligenceResult,
} from "../types/meetingTypes";

type UseMeetingStatusSyncArgs = {
  applyChatHistory: (messages: MeetingChatMessage[]) => void;
  abortControllerRef: RefObject<AbortController | null>;
  checkPendingAnswer: (
    meetingId: string,
    messages: MeetingChatMessage[],
    pendingChatStatus?: string | null,
  ) => Promise<void>;
  currentMeetingIdRef: RefObject<string | null>;
  meetings: Meeting[];
  run: (operation: () => Promise<void>) => Promise<void>;
  selectedMeeting: Meeting | null;
  setChatMessages: Dispatch<SetStateAction<MeetingChatMessage[]>>;
  setHasLoadedMeetings: Dispatch<SetStateAction<boolean>>;
  setIntelligenceResult: Dispatch<SetStateAction<MeetingIntelligenceResult | null>>;
  setLastAsset: Dispatch<SetStateAction<MeetingAsset | null>>;
  setMeetings: Dispatch<SetStateAction<Meeting[]>>;
  token: string;
};

export function useMeetingStatusSync({
  applyChatHistory,
  abortControllerRef,
  checkPendingAnswer,
  currentMeetingIdRef,
  meetings,
  run,
  selectedMeeting,
  setChatMessages,
  setHasLoadedMeetings,
  setIntelligenceResult,
  setLastAsset,
  setMeetings,
  token,
}: UseMeetingStatusSyncArgs) {
  const prevSelectedStatusRef = useRef<string | null>(null);

  const refreshSelectedMeetingState = useCallback(
    async (meeting: Meeting): Promise<Meeting | null> => {
      const detail = await getMeeting(token, meeting.id, { signal: abortControllerRef.current?.signal });
      if (currentMeetingIdRef.current !== meeting.id) {
        return null;
      }
      setMeetings((current) => current.map((item) => (item.id === detail.id ? detail : item)));
      setLastAsset(detail.latestAsset);
      if (detail.status === "READY") {
        const [intelligenceResult, chatHistory] = await Promise.all([
          getMeetingIntelligenceResult(token, meeting.id, { signal: abortControllerRef.current?.signal }),
          getMeetingChatHistory(token, meeting.id),
        ]);
        if (currentMeetingIdRef.current !== meeting.id) {
          return null;
        }
        setIntelligenceResult(intelligenceResult);
        applyChatHistory(chatHistory.messages);
        await checkPendingAnswer(meeting.id, chatHistory.messages, detail.pendingChatStatus);
      } else if (detail.status === "QUEUED" || detail.status === "PROCESSING") {
        const chatHistory = await getMeetingChatHistory(token, meeting.id);
        if (currentMeetingIdRef.current !== meeting.id) {
          return null;
        }
        setIntelligenceResult(null);
        applyChatHistory(chatHistory.messages);
        await checkPendingAnswer(meeting.id, chatHistory.messages, detail.pendingChatStatus);
      } else {
        setIntelligenceResult(null);
        setChatMessages([]);
      }
      return currentMeetingIdRef.current === meeting.id ? detail : null;
    },
    [
      abortControllerRef,
      applyChatHistory,
      checkPendingAnswer,
      currentMeetingIdRef,
      setChatMessages,
      setIntelligenceResult,
      setLastAsset,
      setMeetings,
      token,
    ]
  );

  const pollMeetings = useCallback(async () => {
    const nextMeetings = await listMeetings(token, { signal: abortControllerRef.current?.signal });
    const selectedId = currentMeetingIdRef.current;
    const nextSelected = selectedId ? nextMeetings.find((m) => m.id === selectedId) ?? null : null;
    const prevStatus = prevSelectedStatusRef.current;
    const nextStatus = nextSelected?.status ?? null;

    setMeetings(nextMeetings);
    setHasLoadedMeetings(true);

    if (selectedId && nextSelected && ((prevStatus && prevStatus !== nextStatus) || (!prevStatus && (nextStatus === "QUEUED" || nextStatus === "PROCESSING")))) {
      if (nextStatus === "READY") {
        const [intelligenceResult, chatHistory] = await Promise.all([
          getMeetingIntelligenceResult(token, selectedId, { signal: abortControllerRef.current?.signal }),
          getMeetingChatHistory(token, selectedId),
        ]);
        if (currentMeetingIdRef.current !== selectedId) return;
        setIntelligenceResult(intelligenceResult);
        applyChatHistory(chatHistory.messages);
        setLastAsset(nextSelected.latestAsset);
        await checkPendingAnswer(selectedId, chatHistory.messages, nextSelected?.pendingChatStatus);
      } else if (nextStatus !== "QUEUED" && nextStatus !== "PROCESSING") {
        if (currentMeetingIdRef.current !== selectedId) return;
        setIntelligenceResult(null);
        setChatMessages([]);
      } else {
        const chatHistory = await getMeetingChatHistory(token, selectedId);
        if (currentMeetingIdRef.current !== selectedId) return;
        applyChatHistory(chatHistory.messages);
        setLastAsset(nextSelected.latestAsset);
        await checkPendingAnswer(selectedId, chatHistory.messages, nextSelected?.pendingChatStatus);
      }
    }
    if (nextSelected) {
      prevSelectedStatusRef.current = nextStatus;
    }
  }, [
    abortControllerRef,
    applyChatHistory,
    checkPendingAnswer,
    currentMeetingIdRef,
    setChatMessages,
    setHasLoadedMeetings,
    setIntelligenceResult,
    setLastAsset,
    setMeetings,
    token,
  ]);

  useEffect(() => {
    if (!selectedMeeting) {
      prevSelectedStatusRef.current = null;
      return;
    }
    prevSelectedStatusRef.current = selectedMeeting.status;
    void run(async () => {
      await refreshSelectedMeetingState(selectedMeeting);
    });
  }, [refreshSelectedMeetingState, run, selectedMeeting?.id]);

  const anyProcessing = meetings.some((m) => isProcessingMeeting(m));
  const intervalMs = anyProcessing ? 1000 : 5000;
  useEffect(() => {
    void pollMeetings();
  }, [pollMeetings]);
  usePollingEffect(() => void pollMeetings(), intervalMs);

  return {
    refreshSelectedMeetingState,
  };
}
