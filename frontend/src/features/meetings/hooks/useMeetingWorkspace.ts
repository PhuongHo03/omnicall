import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  askMeetingChat,
  createMeeting,
  deleteMeetingSession,
  downloadMeetingAsset,
  getMeetingChatHistory,
  getMeeting,
  listMeetings,
  queueMeetingProcessing,
  updateMeetingTitle,
  uploadMeetingAsset
} from "../api/meetingApi";
import type {
  Meeting,
  MeetingAsset,
  MeetingChatMessage,
  MeetingIntelligenceResult,
} from "../types/meetingTypes";
import { createClientId } from "../../../shared/utils/id";
import {
  isProcessableMeeting,
  isUploadableMeeting,
} from "../states/meetingState";
import {
  createOptimisticChatMessage,
} from "../states/chatState";
import { useMeetingAssetPlayback } from "./useMeetingAssetPlayback";
import { useMeetingChatWatch } from "./useMeetingChatWatch";
import { useMeetingRecording } from "./useMeetingRecording";
import { useMeetingSelection } from "./useMeetingSelection";
import { useMeetingStatusSync } from "./useMeetingStatusSync";
import { extractTranscriptEntries } from "../utils/meetingTranscript";
import { downloadBlob } from "../../../shared/utils/browserDownload";

function requestKey(prefix: string) {
  return `${prefix}:${createClientId()}`;
}

function isNetworkLikeError(caught: unknown) {
  if (caught instanceof TypeError) {
    return true;
  }
  if (!(caught instanceof Error)) {
    return false;
  }
  return /network|fetch|load failed|failed to fetch|connection/i.test(caught.message);
}

export function useMeetingWorkspace(
  token: string,
  requestedMeetingId: string | null,
  onSelectedMeetingChange: (meetingId: string | null) => void
) {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [lastAsset, setLastAsset] = useState<MeetingAsset | null>(null);
  const [intelligenceResult, setIntelligenceResult] = useState<MeetingIntelligenceResult | null>(null);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatMessages, setChatMessages] = useState<MeetingChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasLoadedMeetings, setHasLoadedMeetings] = useState(false);
  const [typewriterMessageIds, setTypewriterMessageIds] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const {
    abortControllerRef,
    currentMeetingIdRef,
    selectedMeeting,
    selectedMeetingId,
    selectMeeting,
  } = useMeetingSelection({
    hasLoadedMeetings,
    meetings,
    onSelectedMeetingChange,
    requestedMeetingId,
  });

  const run = useCallback(async (operation: () => Promise<void>) => {
    setIsLoading(true);
    setError(null);
    setNotice(null);
    try {
      await operation();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Request failed.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const playbackError = useCallback((message: string) => {
    setError(message);
  }, []);

  const { startChatWatch, stopChatWatch } = useMeetingChatWatch({
    currentMeetingIdRef,
    setChatMessages,
    setTypewriterMessageIds,
    token,
  });

  const assetPlaybackUrl = useMeetingAssetPlayback(
    token,
    selectedMeeting,
    lastAsset,
    playbackError,
  );

  const refreshMeetings = useCallback(async () => {
    const nextMeetings = await listMeetings(token);
    setMeetings(nextMeetings);
    setHasLoadedMeetings(true);
  }, [token]);

  useEffect(() => {
    stopChatWatch();
    setChatQuestion("");
    setChatMessages([]);
    setLastAsset(null);
    setIntelligenceResult(null);
  }, [selectedMeetingId, stopChatWatch]);

  const checkPendingAnswer = useCallback(async (
    meetingId: string,
    messages: MeetingChatMessage[],
    pendingChatStatus?: string | null,
  ): Promise<void> => {
    const lastMessage = messages[messages.length - 1];
    if (!lastMessage || lastMessage.role !== "user") {
      return;
    }
    // Guard: don't create duplicate optimistic messages
    stopChatWatch();
    let ragStatus = pendingChatStatus;
    if (ragStatus === undefined) {
      try {
        const detail = await getMeeting(token, meetingId, { signal: abortControllerRef.current?.signal });
        ragStatus = detail.pendingChatStatus;
      } catch {
        ragStatus = "started";
      }
    }
    if (!ragStatus) {
      // RAG task is not pending — don't create optimistic message
      return;
    }
    const initialMessage = ragStatus === "queued" ? "Đang chờ xử lý..." : "Đang xử lý...";
    const optimisticAssistant = createOptimisticChatMessage("assistant", initialMessage);
    setChatMessages((current) => [...current, optimisticAssistant]);
    startChatWatch(meetingId, { statusMessageId: optimisticAssistant.id });
  }, [startChatWatch, token]);
  const { refreshSelectedMeetingState } = useMeetingStatusSync({
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
  });

  const createNewMeeting = useCallback(() => {
    void run(async () => {
      const created = await createMeeting(token);
      setMeetings((current) => [created, ...current]);
      selectMeeting(created.id);
      setLastAsset(null);
      setIntelligenceResult(null);
      setNotice("Meeting created.");
    });
  }, [run, selectMeeting, token]);

  const renameSelectedMeeting = useCallback(
    (title: string) => {
      if (!selectedMeeting) {
        setError("Select a meeting first.");
        return;
      }
      void run(async () => {
        const updated = await updateMeetingTitle(token, selectedMeeting.id, title);
        setMeetings((current) => current.map((item) => (item.id === updated.id ? updated : item)));
        setNotice("Meeting renamed.");
      });
    },
    [run, selectedMeeting, token]
  );

  const uploadFile = useCallback(
    (file: File) => {
      if (!selectedMeeting) {
        setError("Select a meeting first.");
        return;
      }
      if (!isUploadableMeeting(selectedMeeting, lastAsset)) {
        setError("This meeting already has an uploaded file or processing output. Create a new meeting to upload another file.");
        return;
      }
      void run(async () => {
        const asset = await uploadMeetingAsset(token, selectedMeeting.id, file, requestKey("upload"));
        setLastAsset(asset);
        setNotice("Upload completed.");
        await refreshMeetings();
      });
    },
    [lastAsset, refreshMeetings, run, selectedMeeting, token]
  );

  const recording = useMeetingRecording({
    lastAsset,
    run,
    selectedMeeting,
    setError,
    setNotice,
    uploadFile,
  });

  const queueProcessing = useCallback(() => {
    if (!selectedMeeting) {
      setError("Select a meeting first.");
      return;
    }
    if (!isProcessableMeeting(selectedMeeting, lastAsset)) {
      setError("Upload a meeting file before starting processing.");
      return;
    }
    void run(async () => {
      const meeting = await queueMeetingProcessing(token, selectedMeeting.id, requestKey("process"));
      setMeetings((current) => current.map((item) => (item.id === meeting.id ? meeting : item)));
      setNotice(meeting.status === "FAILED" ? "Processing could not be queued." : "Processing queued.");
    });
  }, [lastAsset, run, selectedMeeting, token]);

  const refreshStatus = useCallback(() => {
    if (!selectedMeeting) {
      setError("Select a meeting first.");
      return;
    }
    void run(async () => {
      await refreshSelectedMeetingState(selectedMeeting);
      setNotice("Status refreshed.");
    });
  }, [refreshSelectedMeetingState, run, selectedMeeting]);

  const submitChatQuestion = useCallback(() => {
    if (!selectedMeeting) {
      setError("Select a meeting first.");
      return;
    }
    if (selectedMeeting.status !== "READY") {
      setError("Meeting must be ready before chat is available.");
      return;
    }
    const question = chatQuestion.trim();
    if (!question) {
      setError("Question must not be empty.");
      return;
    }
    const optimisticQuestion = createOptimisticChatMessage("user", question);
    setChatQuestion("");
    setChatMessages((current) => [...current, optimisticQuestion]);

    void run(async () => {
      try {
        await askMeetingChat(token, selectedMeeting.id, question);
      } catch (caught) {
        if (!isNetworkLikeError(caught)) {
          const history = await getMeetingChatHistory(token, selectedMeeting.id);
          setChatMessages(history.messages);
          throw caught;
        }
        setChatMessages((current) =>
          current.filter((item) => item.id !== optimisticQuestion.id)
        );
        throw caught;
      }
    });

    stopChatWatch();
    const optimisticAssistant = createOptimisticChatMessage("assistant", "Đang chờ xử lý...");
    setChatMessages((current) => [...current, optimisticAssistant]);
    startChatWatch(selectedMeeting.id, { statusMessageId: optimisticAssistant.id });
  }, [chatQuestion, run, selectedMeeting, token]);

  const refreshChatHistory = useCallback(() => {
    if (!selectedMeeting) {
      return;
    }
    void run(async () => {
      const history = await getMeetingChatHistory(token, selectedMeeting.id);
      setChatMessages(history.messages);
      checkPendingAnswer(selectedMeeting.id, history.messages, selectedMeeting.pendingChatStatus);
      setNotice("Chat refreshed.");
    });
  }, [run, selectedMeeting, token]);

  const deleteSelectedMeeting = useCallback(() => {
    if (!selectedMeeting) {
      setError("Select a meeting first.");
      return;
    }
    void run(async () => {
      await deleteMeetingSession(token, selectedMeeting.id);
      setMeetings((current) => current.filter((item) => item.id !== selectedMeeting.id));
      selectMeeting(null);
      setLastAsset(null);
      setIntelligenceResult(null);
      setNotice("Meeting session deleted.");
    });
  }, [run, selectMeeting, selectedMeeting, token]);

  const transcriptEntries = useMemo(() => extractTranscriptEntries(intelligenceResult), [intelligenceResult]);

  const downloadAsset = useCallback(() => {
    if (!selectedMeeting || !lastAsset) return;
    void run(async () => {
      const blob = await downloadMeetingAsset(token, selectedMeeting.id, lastAsset.id);
      downloadBlob(blob, lastAsset.fileName);
    });
  }, [run, selectedMeeting, lastAsset, token]);

  const canUpload = selectedMeeting ? isUploadableMeeting(selectedMeeting, lastAsset) : false;
  const canProcess = selectedMeeting ? isProcessableMeeting(selectedMeeting, lastAsset) : false;
  const hasLockedAsset = Boolean(lastAsset);

  return {
    assetPlaybackUrl,
    canProcess,
    canUpload,
    downloadAsset,
    transcriptEntries,
    chatMessages,
    chatQuestion,
    error,
    hasLockedAsset,
    intelligenceResult,
    isLoading,
    isRecording: recording.isRecording,
    lastAsset,
    meetings,
    notice,
    selectedMeeting,
    selectedMeetingId,
    createNewMeeting,
    queueProcessing,
    deleteSelectedMeeting,
    refreshChatHistory,
    refreshMeetings: () => void run(refreshMeetings),
    refreshStatus,
    setChatQuestion,
    setSelectedMeetingId: selectMeeting,
    startRecording: recording.startRecording,
    stopRecording: recording.stopRecording,
    submitChatQuestion,
    renameSelectedMeeting,
    uploadFile,
    typewriterMessageIds,
    clearTypewriterId: (id: string) => {
      setTypewriterMessageIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    },
  };
}
