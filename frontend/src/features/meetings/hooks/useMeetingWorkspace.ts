import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  askMeetingChat,
  createMeeting,
  deleteMeetingSession,
  downloadMeetingAsset,
  getMeetingChatHistory,
  getMeeting,
  isChatBusyError,
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
  restoreRejectedChatQuestion,
} from "../states/chatState";
import { useMeetingAssetPlayback } from "./useMeetingAssetPlayback";
import { useChatFeedback } from "./useChatFeedback";
import { useMeetingChatWatch } from "./useMeetingChatWatch";
import { useMeetingRecording } from "./useMeetingRecording";
import { useMeetingSelection } from "./useMeetingSelection";
import { useMeetingStatusSync } from "./useMeetingStatusSync";
import { extractTranscriptEntries } from "../utils/meetingTranscript";
import { downloadBlob } from "../../../shared/utils/browserDownload";
import { useToast } from "../../../shared/layouts/ToastContext";

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
  ownerId: string,
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
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [hasLoadedMeetings, setHasLoadedMeetings] = useState(false);
  const lockedMeetingIdRef = useRef<string | null>(null);
  const operationLockedRef = useRef(false);
  const [typewriterMessageIds, setTypewriterMessageIds] = useState<Set<string>>(new Set());
  const { showToast } = useToast();
  const showNotice = useCallback((message: string) => {
    showToast({ message, tone: "success" });
  }, [showToast]);
  const showError = useCallback((message: string) => {
    showToast({ message, tone: "error" });
  }, [showToast]);
  const {
    abortControllerRef,
    currentMeetingIdRef,
    selectedMeeting,
    selectedMeetingId,
    selectMeeting,
  } = useMeetingSelection({
    hasLoadedMeetings,
    lockedMeetingIdRef,
    meetings,
    onSelectedMeetingChange,
    requestedMeetingId,
  });

  const {
    applyChatHistory,
    pendingFeedbackMessageIds,
    submitChatFeedback,
  } = useChatFeedback({
    meetingId: selectedMeetingId,
    messages: chatMessages,
    onError: showError,
    setMessages: setChatMessages,
    token,
  });

  const run = useCallback(async (operation: () => Promise<void>) => {
    setIsLoading(true);
    try {
      await operation();
    } catch (caught) {
      showError(caught instanceof Error ? caught.message : "Request failed.");
    } finally {
      setIsLoading(false);
    }
  }, [showError]);

  const playbackError = useCallback((message: string) => {
    showError(message);
  }, [showError]);

  const { startChatWatch, stopChatWatch } = useMeetingChatWatch({
    applyChatHistory,
    currentMeetingIdRef,
    setChatMessages,
    setTypewriterMessageIds,
    token,
  });

  const assetPlayback = useMeetingAssetPlayback(
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
  });

  const createNewMeeting = useCallback(() => {
    if (operationLockedRef.current) {
      showError("Resolve the current recording or upload before creating another meeting.");
      return;
    }
    void run(async () => {
      const created = await createMeeting(token);
      setMeetings((current) => [created, ...current]);
      selectMeeting(created.id);
      setLastAsset(null);
      setIntelligenceResult(null);
      showNotice("Meeting created.");
    });
  }, [run, selectMeeting, showError, showNotice, token]);

  const renameSelectedMeeting = useCallback(
    (title: string) => {
      if (operationLockedRef.current) {
        showError("Resolve the current recording or upload before renaming this meeting.");
        return;
      }
      if (!selectedMeeting) {
        showError("Select a meeting first.");
        return;
      }
      void run(async () => {
        const updated = await updateMeetingTitle(token, selectedMeeting.id, title);
        setMeetings((current) => current.map((item) => (item.id === updated.id ? updated : item)));
        showNotice("Meeting renamed.");
      });
    },
    [run, selectedMeeting, showError, showNotice, token]
  );

  const uploadFileToMeeting = useCallback(async (meetingId: string, file: File): Promise<MeetingAsset> => {
    const targetMeeting = meetings.find((meeting) => meeting.id === meetingId);
    if (!targetMeeting || targetMeeting.status !== "DRAFT" || targetMeeting.latestAsset) {
      throw new Error("This meeting cannot accept another file.");
    }
    setUploadProgress(0);
    try {
      const asset = await uploadMeetingAsset(token, meetingId, file, requestKey("upload"), setUploadProgress);
      if (currentMeetingIdRef.current === meetingId) {
        setLastAsset(asset);
      }
      await refreshMeetings();
      return asset;
    } finally {
      setUploadProgress(null);
    }
  }, [currentMeetingIdRef, meetings, refreshMeetings, token]);

  const recording = useMeetingRecording({
    hasLoadedMeetings,
    lastAsset,
    meetings,
    onSelectMeeting: selectMeeting,
    ownerId,
    selectedMeeting,
    setError: showError,
    setNotice: showNotice,
    uploadFileToMeeting,
  });
  lockedMeetingIdRef.current = recording.lockedMeetingId;
  const isOperationLocked = recording.isLocked || uploadProgress !== null;
  operationLockedRef.current = isOperationLocked;

  const uploadFile = useCallback((file: File) => {
    if (!selectedMeeting) {
      showError("Select a meeting first.");
      return;
    }
    if (operationLockedRef.current || !isUploadableMeeting(selectedMeeting, lastAsset)) {
      showError("Resolve the current recording or upload before selecting another file.");
      return;
    }
    void run(async () => {
      await uploadFileToMeeting(selectedMeeting.id, file);
      showNotice("Upload completed.");
    });
  }, [lastAsset, run, selectedMeeting, showError, showNotice, uploadFileToMeeting]);

  const queueProcessing = useCallback(() => {
    if (operationLockedRef.current) {
      showError("Resolve the current recording or upload before processing.");
      return;
    }
    if (!selectedMeeting) {
      showError("Select a meeting first.");
      return;
    }
    if (!isProcessableMeeting(selectedMeeting, lastAsset)) {
      showError("Upload a meeting file before starting processing.");
      return;
    }
    void run(async () => {
      const meeting = await queueMeetingProcessing(token, selectedMeeting.id, requestKey("process"));
      setMeetings((current) => current.map((item) => (item.id === meeting.id ? meeting : item)));
      if (meeting.status === "FAILED") {
        showError("Processing could not be queued.");
      } else {
        showNotice("Processing queued.");
      }
    });
  }, [lastAsset, run, selectedMeeting, showError, showNotice, token]);

  const refreshStatus = useCallback(() => {
    if (operationLockedRef.current) {
      showError("Resolve the current recording or upload before refreshing.");
      return;
    }
    if (!selectedMeeting) {
      showError("Select a meeting first.");
      return;
    }
    void run(async () => {
      const refreshedMeeting = await refreshSelectedMeetingState(selectedMeeting);
      if (refreshedMeeting) {
        showNotice(refreshedMeeting.status === "READY" ? "Chat refreshed." : "Status refreshed.");
      }
    });
  }, [refreshSelectedMeetingState, run, selectedMeeting, showError, showNotice]);

  const submitChatQuestion = useCallback(() => {
    if (!selectedMeeting) {
      showError("Select a meeting first.");
      return;
    }
    if (selectedMeeting.status !== "READY") {
      showError("Meeting must be ready before chat is available.");
      return;
    }
    const question = chatQuestion.trim();
    if (!question) {
      showError("Question must not be empty.");
      return;
    }
    const optimisticQuestion = createOptimisticChatMessage("user", question);
    setChatQuestion("");
    setChatMessages((current) => [...current, optimisticQuestion]);

    void run(async () => {
      try {
        const accepted = await askMeetingChat(token, selectedMeeting.id, question);
        if (accepted.status === "clarification_needed") {
          const history = await getMeetingChatHistory(token, selectedMeeting.id);
          applyChatHistory(history.messages);
          return;
        }
        stopChatWatch();
        const optimisticAssistant = createOptimisticChatMessage("assistant", "Đang chờ xử lý...");
        setChatMessages((current) => [...current, optimisticAssistant]);
        startChatWatch(selectedMeeting.id, { turnId: accepted.turnId, statusMessageId: optimisticAssistant.id });
      } catch (caught) {
        setChatQuestion((current) => restoreRejectedChatQuestion(current, question));
        if (isChatBusyError(caught)) {
          try {
            const history = await getMeetingChatHistory(token, selectedMeeting.id);
            applyChatHistory(history.messages);
            await checkPendingAnswer(selectedMeeting.id, history.messages);
          } catch {
            setChatMessages((current) => current.filter((item) => item.id !== optimisticQuestion.id));
          }
          throw new Error(caught.message || "Another question is still being processed. Your question was kept.");
        }
        if (!isNetworkLikeError(caught)) {
          try {
            const history = await getMeetingChatHistory(token, selectedMeeting.id);
            applyChatHistory(history.messages);
          } catch {
            setChatMessages((current) => current.filter((item) => item.id !== optimisticQuestion.id));
          }
          throw caught;
        }
        setChatMessages((current) => current.filter((item) => item.id !== optimisticQuestion.id));
        throw caught;
      }
    });
  }, [applyChatHistory, chatQuestion, checkPendingAnswer, run, selectedMeeting, showError, startChatWatch, stopChatWatch, token]);

  const refreshChatHistory = useCallback(() => {
    if (!selectedMeeting) {
      return;
    }
    void run(async () => {
      const history = await getMeetingChatHistory(token, selectedMeeting.id);
      applyChatHistory(history.messages);
      checkPendingAnswer(selectedMeeting.id, history.messages, selectedMeeting.pendingChatStatus);
    });
  }, [applyChatHistory, checkPendingAnswer, run, selectedMeeting, token]);

  const deleteSelectedMeeting = useCallback(() => {
    if (operationLockedRef.current) {
      showError("Resolve the current recording or upload before deleting this meeting.");
      return;
    }
    if (!selectedMeeting) {
      showError("Select a meeting first.");
      return;
    }
    void run(async () => {
      await deleteMeetingSession(token, selectedMeeting.id);
      setMeetings((current) => current.filter((item) => item.id !== selectedMeeting.id));
      selectMeeting(null);
      setLastAsset(null);
      setIntelligenceResult(null);
      showNotice("Meeting session deleted.");
    });
  }, [run, selectMeeting, selectedMeeting, showError, showNotice, token]);

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
    assetPlaybackUrl: assetPlayback.url,
    assetPlaybackStatus: assetPlayback.status,
    assetPlaybackError: assetPlayback.error,
    canProcess,
    canUpload,
    downloadAsset,
    transcriptEntries,
    chatMessages,
    chatQuestion,
    hasLockedAsset,
    intelligenceResult,
    isLoading,
    isOperationLocked,
    isRecording: recording.isRecording,
    recordingSession: recording.session,
    lastAsset,
    uploadProgress,
    meetings,
    selectedMeeting,
    selectedMeetingId,
    pendingFeedbackMessageIds,
    createNewMeeting,
    queueProcessing,
    deleteSelectedMeeting,
    refreshChatHistory,
    refreshMeetings: () => void run(refreshMeetings),
    refreshStatus,
    setChatQuestion,
    setSelectedMeetingId: selectMeeting,
    discardRecording: recording.discardRecording,
    downloadRecording: recording.downloadRecording,
    retryRecordingUpload: recording.retryUpload,
    startRecording: recording.startRecording,
    stopRecording: recording.stopRecording,
    submitChatQuestion,
    submitChatFeedback,
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
