import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  askMeetingChat,
  createMeeting,
  deleteMeetingSession,
  downloadMeetingAsset,
  getMeetingIntelligenceResult,
  getMeetingChatHistory,
  getMeeting,
  listMeetings,
  queueMeetingProcessing,
  streamChatEvents,
  updateMeetingTitle,
  uploadMeetingAsset
} from "../api/meetingApi";
import type { ChatStreamEvent } from "../api/meetingApi";
import type {
  Meeting,
  MeetingAsset,
  MeetingChatMessage,
  MeetingIntelligenceResult,
} from "../types/meetingTypes";
import type { TranscriptEntry } from "../types/meetingTypes";
import { createClientId } from "../../../shared/utils/id";

function requestKey(prefix: string) {
  return `${prefix}:${createClientId()}`;
}

function isUploadableMeeting(meeting: Meeting, asset: MeetingAsset | null) {
  return meeting.status === "DRAFT" && asset === null;
}

function isProcessableMeeting(meeting: Meeting, asset: MeetingAsset | null) {
  if (!asset) {
    return false;
  }
  return meeting.status === "UPLOADED" || meeting.status === "FAILED";
}

function isProcessingMeeting(meeting: Meeting | null) {
  return meeting?.status === "QUEUED" || meeting?.status === "PROCESSING";
}

function isAudioAsset(asset: MeetingAsset | null) {
  return asset?.contentType.startsWith("audio/") === true;
}


function normalizeChatContent(value: string) {
  return value.trim().replace(/\s+/g, " ");
}

function isMessageAfter(message: MeetingChatMessage, minCreatedAtMs: number | null) {
  if (minCreatedAtMs === null) {
    return true;
  }
  const createdAtMs = Date.parse(message.createdAt);
  return Number.isNaN(createdAtMs) ? true : createdAtMs >= minCreatedAtMs;
}

function findQuestionMessageIndex(messages: MeetingChatMessage[], question: string, minCreatedAtMs: number | null = null) {
  const normalizedQuestion = normalizeChatContent(question);
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (
      message.role === "user" &&
      isMessageAfter(message, minCreatedAtMs) &&
      normalizeChatContent(message.content) === normalizedQuestion
    ) {
      return index;
    }
  }
  return -1;
}

function findAssistantAnswerAfterQuestion(
  messages: MeetingChatMessage[],
  question: string,
  minCreatedAtMs: number | null = null
) {
  const questionIndex = findQuestionMessageIndex(messages, question, minCreatedAtMs);
  if (questionIndex < 0) {
    return null;
  }
  return messages.slice(questionIndex + 1).find((message) => message.role === "assistant") ?? null;
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

function wait(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function createOptimisticChatMessage(role: "user" | "assistant", content: string): MeetingChatMessage {
  return {
    id: `local:${createClientId()}`,
    role,
    content,
    retrievedChunkIds: [],
    citations: [],
    metadata: { local: true, pending: role === "assistant" },
    createdAt: new Date().toISOString()
  };
}


export function useMeetingWorkspace(
  token: string,
  requestedMeetingId: string | null,
  onSelectedMeetingChange: (meetingId: string | null) => void
) {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(requestedMeetingId);
  const [lastAsset, setLastAsset] = useState<MeetingAsset | null>(null);
  const [assetPlaybackUrl, setAssetPlaybackUrl] = useState<string | null>(null);
  const [intelligenceResult, setIntelligenceResult] = useState<MeetingIntelligenceResult | null>(null);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatMessages, setChatMessages] = useState<MeetingChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasLoadedMeetings, setHasLoadedMeetings] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [typewriterMessageIds, setTypewriterMessageIds] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const currentMeetingIdRef = useRef<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingChunksRef = useRef<BlobPart[]>([]);
  const chatPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sseCloseRef = useRef<(() => void) | null>(null);
  const prevSelectedStatusRef = useRef<string | null>(null);

  const selectedMeeting = useMemo(
    () => meetings.find((meeting) => meeting.id === selectedMeetingId) ?? null,
    [meetings, selectedMeetingId]
  );

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

  const selectMeeting = useCallback(
    (meetingId: string | null) => {
      setSelectedMeetingId(meetingId);
      onSelectedMeetingChange(meetingId);
    },
    [onSelectedMeetingChange]
  );

  const refreshMeetings = useCallback(async () => {
    const nextMeetings = await listMeetings(token);
    setMeetings(nextMeetings);
    setHasLoadedMeetings(true);
  }, [token]);


  useEffect(() => {
    if (!hasLoadedMeetings) {
      return;
    }
    if (!requestedMeetingId) {
      setSelectedMeetingId(null);
      return;
    }
    if (meetings.some((meeting) => meeting.id === requestedMeetingId)) {
      setSelectedMeetingId(requestedMeetingId);
      return;
    }
    setSelectedMeetingId(null);
    onSelectedMeetingChange(null);
  }, [hasLoadedMeetings, meetings, onSelectedMeetingChange, requestedMeetingId]);

  useEffect(() => {
    currentMeetingIdRef.current = selectedMeetingId;
      setChatQuestion("");
    setChatMessages([]);
    setLastAsset(null);
    setAssetPlaybackUrl(null);
    setIntelligenceResult(null);
  }, [selectedMeetingId]);

  useEffect(() => {
    if (!selectedMeeting || !lastAsset || !isAudioAsset(lastAsset) || lastAsset.meetingId !== selectedMeeting.id) {
      setAssetPlaybackUrl(null);
      return;
    }

    let isActive = true;
    let objectUrl: string | null = null;
    void downloadMeetingAsset(token, selectedMeeting.id, lastAsset.id)
      .then((blob) => {
        if (!isActive) {
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setAssetPlaybackUrl(objectUrl);
      })
      .catch((caught) => {
        if (isActive) {
          setAssetPlaybackUrl(null);
          setError(caught instanceof Error ? caught.message : "Asset playback failed.");
        }
      });

    return () => {
      isActive = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [lastAsset?.id, selectedMeeting?.id, token]);

  const startChatWatch = useCallback((meetingId: string, options?: { statusMessageId?: string }) => {
    const statusMessageId = options?.statusMessageId ?? null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT = 3;
    const RECONNECT_DELAY_MS = 2000;

    const cleanup = () => {
      if (sseCloseRef.current) {
        sseCloseRef.current();
        sseCloseRef.current = null;
      }
      if (chatPollingRef.current) {
        clearInterval(chatPollingRef.current);
        chatPollingRef.current = null;
      }
    };

    cleanup();

    const connectSse = () => {
      if (currentMeetingIdRef.current !== meetingId) return;

      const closeSse = streamChatEvents(token, meetingId, (event: ChatStreamEvent) => {
        if (currentMeetingIdRef.current !== meetingId) return;
        reconnectAttempts = 0; // Reset on successful event
        if (event.type === "status" && statusMessageId) {
          setChatMessages((current) =>
            current.map((item) =>
              item.id === statusMessageId
                ? { ...item, content: event.message }
                : item
            )
          );
        } else if (event.type === "done" || event.type === "blocked") {
          cleanup();
          void getMeetingChatHistory(token, meetingId).then((history) => {
            setChatMessages(history.messages);
            const lastMsg = history.messages[history.messages.length - 1];
            if (lastMsg && lastMsg.role === "assistant") {
              setTypewriterMessageIds((prev) => new Set(prev).add(lastMsg.id));
            }
          });
        }
      }, undefined, () => {
        // SSE ended — try reconnect if still waiting
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

    // Polling for reliable answer detection
    chatPollingRef.current = setInterval(() => {
      if (currentMeetingIdRef.current !== meetingId) {
        cleanup();
        return;
      }
      void getMeetingChatHistory(token, meetingId).then((history) => {
        const lastMsg = history.messages[history.messages.length - 1];
        if (lastMsg && lastMsg.role === "assistant" && !lastMsg.metadata.pending) {
          cleanup();
          setChatMessages(history.messages);
          setTypewriterMessageIds((prev) => new Set(prev).add(lastMsg.id));
        }
      });
    }, 3000);
  }, [token]);

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
        const detail = await getMeeting(token, meetingId);
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
  }, [startChatWatch, stopChatWatch, token]);
  const pollMeetings = useCallback(async () => {
    const nextMeetings = await listMeetings(token);
    const selectedId = currentMeetingIdRef.current;
    const nextSelected = selectedId ? nextMeetings.find((m) => m.id === selectedId) ?? null : null;
    const prevStatus = prevSelectedStatusRef.current;
    const nextStatus = nextSelected?.status ?? null;

    setMeetings(nextMeetings);
    setHasLoadedMeetings(true);

    if (selectedId && nextSelected && ((prevStatus && prevStatus !== nextStatus) || (!prevStatus && (nextStatus === "QUEUED" || nextStatus === "PROCESSING")))) {
      if (nextStatus === "READY") {
        const [intelligenceResult, chatHistory] = await Promise.all([
          getMeetingIntelligenceResult(token, selectedId),
          getMeetingChatHistory(token, selectedId),
        ]);
        if (currentMeetingIdRef.current !== selectedId) return;
        setIntelligenceResult(intelligenceResult);
        setChatMessages(chatHistory.messages);
        setLastAsset(nextSelected.latestAsset);
        checkPendingAnswer(selectedId, chatHistory.messages, nextSelected?.pendingChatStatus);
      } else if (nextStatus !== "QUEUED" && nextStatus !== "PROCESSING") {
        if (currentMeetingIdRef.current !== selectedId) return;
        setIntelligenceResult(null);
        setChatMessages([]);
      } else {
        // QUEUED or PROCESSING on first load — start watching for answer
        const chatHistory = await getMeetingChatHistory(token, selectedId);
        if (currentMeetingIdRef.current !== selectedId) return;
        setChatMessages(chatHistory.messages);
        setLastAsset(nextSelected.latestAsset);
        checkPendingAnswer(selectedId, chatHistory.messages, nextSelected?.pendingChatStatus);
      }
    }
    if (nextSelected) {
      prevSelectedStatusRef.current = nextStatus;
    }
  }, [token, checkPendingAnswer]);


  const refreshSelectedMeetingState = useCallback(
    async (meeting: Meeting) => {
      const detail = await getMeeting(token, meeting.id);
      if (currentMeetingIdRef.current !== meeting.id) {
        return;
      }
      setMeetings((current) => current.map((item) => (item.id === detail.id ? detail : item)));
      setLastAsset(detail.latestAsset);
      if (detail.status === "READY") {
        const [intelligenceResult, chatHistory] = await Promise.all([
          getMeetingIntelligenceResult(token, meeting.id),
          getMeetingChatHistory(token, meeting.id),
        ]);
        if (currentMeetingIdRef.current !== meeting.id) {
          return;
        }
        setIntelligenceResult(intelligenceResult);
        setChatMessages(chatHistory.messages);
        checkPendingAnswer(meeting.id, chatHistory.messages, detail.pendingChatStatus);
      } else if (detail.status === "QUEUED" || detail.status === "PROCESSING") {
        const chatHistory = await getMeetingChatHistory(token, meeting.id);
        if (currentMeetingIdRef.current !== meeting.id) {
          return;
        }
        setIntelligenceResult(null);
        setChatMessages(chatHistory.messages);
        checkPendingAnswer(meeting.id, chatHistory.messages, detail.pendingChatStatus);
      } else {
        setIntelligenceResult(null);
        setChatMessages([]);
      }
    },
    [token, checkPendingAnswer]
  );

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

  useEffect(() => {
    void pollMeetings();
    const anyProcessing = meetings.some((m) => isProcessingMeeting(m));
    const intervalMs = anyProcessing ? 1000 : 5000;
    const interval = window.setInterval(() => {
      void pollMeetings();
    }, intervalMs);
    return () => window.clearInterval(interval);
  }, [pollMeetings, meetings.some((m) => isProcessingMeeting(m))]);

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

  const startRecording = useCallback(() => {
    if (!selectedMeeting) {
      setError("Select a meeting first.");
      return;
    }
    if (!isUploadableMeeting(selectedMeeting, lastAsset)) {
      setError("This meeting already has an uploaded file or processing output. Create a new meeting to record another file.");
      return;
    }
    void run(async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordingChunksRef.current = [];
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordingChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(recordingChunksRef.current, { type: "audio/webm" });
        const file = new File([blob], `recording-${new Date().toISOString()}.webm`, { type: "audio/webm" });
        uploadFile(file);
      };
      recorder.start();
      setIsRecording(true);
      setNotice("Recording started.");
    });
  }, [lastAsset, run, selectedMeeting, uploadFile]);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
      setIsRecording(false);
      setNotice("Recording stopped.");
    }
  }, []);


  // Extract transcript entries from intelligence result
  const transcriptEntries = useMemo<TranscriptEntry[]>(() => {
    if (!intelligenceResult || typeof intelligenceResult !== "object") return [];
    const transcript = (intelligenceResult as Record<string, unknown>).transcript;
    if (!transcript || typeof transcript !== "object") return [];
    const segments = (transcript as Record<string, unknown>).segments;
    if (!Array.isArray(segments)) return [];
    return segments
      .map((seg: unknown) => {
        const s = seg as Record<string, unknown>;
        return {
          id: String(s.id ?? ""),
          speaker: String(s.speaker ?? "Unknown"),
          startMs: typeof s.startMs === "number" ? s.startMs : 0,
          endMs: typeof s.endMs === "number" ? s.endMs : 0,
          text: String(s.text ?? ""),
        };
      })
      .filter((entry) => entry.id && entry.text);
  }, [intelligenceResult]);

  const downloadAsset = useCallback(() => {
    if (!selectedMeeting || !lastAsset) return;
    void run(async () => {
      const blob = await downloadMeetingAsset(token, selectedMeeting.id, lastAsset.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = lastAsset.fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
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
    isRecording,
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
    startRecording,
    stopRecording,
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
