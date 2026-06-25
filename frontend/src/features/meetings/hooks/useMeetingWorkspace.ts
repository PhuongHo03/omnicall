import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  askMeetingChat,
  createMeeting,
  deleteAccountFile,
  deleteMeetingSession,
  downloadAccountFile,
  downloadMeetingAsset,
  getMeetingIntelligenceResult,
  getMeetingChatHistory,
  getProcessingStatus,
  listAccountFiles,
  listMeetings,
  queueMeetingProcessing,
  uploadAccountFile,
  uploadMeetingAsset
} from "../api/meetingApi";
import type {
  AccountFile,
  Meeting,
  MeetingAsset,
  MeetingChatMessage,
  MeetingDraft,
  MeetingIntelligenceResult,
  ProcessingJob
} from "../types/meetingTypes";
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

const CHAT_RECOVERY_ATTEMPTS = 10;
const CHAT_RECOVERY_DELAY_MS = 3000;
const CHAT_STREAM_MAX_STEPS = 160;
const CHAT_STREAM_STEP_MS = 35;
const CHAT_THINKING_TEXT = "Đang tra cứu...";

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

function buildStreamChunks(content: string) {
  const tokens = content.match(/\S+\s*/g) ?? [content];
  const groupSize = Math.max(1, Math.ceil(tokens.length / CHAT_STREAM_MAX_STEPS));
  const chunks: string[] = [];
  for (let index = 0; index < tokens.length; index += groupSize) {
    chunks.push(tokens.slice(index, index + groupSize).join(""));
  }
  return chunks;
}

export function useMeetingWorkspace(
  token: string,
  requestedMeetingId: string | null,
  onSelectedMeetingChange: (meetingId: string | null) => void
) {
  const [draft, setDraft] = useState<MeetingDraft>({ title: "", language: "vi" });
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [accountFiles, setAccountFiles] = useState<AccountFile[]>([]);
  const [filePlaybackUrl, setFilePlaybackUrl] = useState<string | null>(null);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(requestedMeetingId);
  const [latestJob, setLatestJob] = useState<ProcessingJob | null>(null);
  const [lastAsset, setLastAsset] = useState<MeetingAsset | null>(null);
  const [assetPlaybackUrl, setAssetPlaybackUrl] = useState<string | null>(null);
  const [intelligenceResult, setIntelligenceResult] = useState<MeetingIntelligenceResult | null>(null);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatMessages, setChatMessages] = useState<MeetingChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasLoadedMeetings, setHasLoadedMeetings] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingChunksRef = useRef<BlobPart[]>([]);
  const chatStreamGenerationRef = useRef(0);

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

  const refreshAccountFiles = useCallback(async () => {
    setAccountFiles(await listAccountFiles(token));
  }, [token]);

  useEffect(() => {
    void run(refreshMeetings);
    void run(refreshAccountFiles);
  }, [refreshAccountFiles, refreshMeetings, run]);

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
    chatStreamGenerationRef.current += 1;
    setChatQuestion("");
    setChatMessages([]);
    setLatestJob(null);
    setLastAsset(null);
    setAssetPlaybackUrl(null);
    setIntelligenceResult(null);
  }, [selectedMeetingId]);

  useEffect(() => {
    if (!selectedMeeting || !lastAsset || !isAudioAsset(lastAsset)) {
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

  const refreshSelectedMeetingState = useCallback(
    async (meeting: Meeting) => {
      const status = await getProcessingStatus(token, meeting.id);
      setMeetings((current) => current.map((item) => (item.id === status.meeting.id ? status.meeting : item)));
      setLatestJob(status.latestJob);
      setLastAsset(status.latestAsset);
      if (status.meeting.status === "READY") {
        setIntelligenceResult(await getMeetingIntelligenceResult(token, meeting.id));
        const chatHistory = await getMeetingChatHistory(token, meeting.id);
        setChatMessages(chatHistory.messages);
      } else {
        setIntelligenceResult(null);
        setChatMessages([]);
      }
    },
    [token]
  );

  const streamAssistantMessage = useCallback(async (placeholderId: string, message: MeetingChatMessage) => {
    const generation = chatStreamGenerationRef.current;
    const chunks = buildStreamChunks(message.content);
    let streamedContent = "";

    setChatMessages((current) =>
      current.map((item) =>
        item.id === placeholderId
          ? {
              ...message,
              id: placeholderId,
              content: "",
              citations: [],
              metadata: { ...message.metadata, local: true, streaming: true }
            }
          : item
      )
    );

    for (const chunk of chunks) {
      if (chatStreamGenerationRef.current !== generation) {
        return false;
      }
      streamedContent += chunk;
      setChatMessages((current) =>
        current.map((item) => (item.id === placeholderId ? { ...item, content: streamedContent } : item))
      );
      await wait(CHAT_STREAM_STEP_MS);
    }

    if (chatStreamGenerationRef.current !== generation) {
      return false;
    }

    setChatMessages((current) => current.map((item) => (item.id === placeholderId ? message : item)));
    return true;
  }, []);

  useEffect(() => {
    if (!selectedMeeting) {
      return;
    }
    const meeting = selectedMeeting;
    void run(async () => {
      await refreshSelectedMeetingState(meeting);
    });
  }, [refreshSelectedMeetingState, run, selectedMeeting?.id]);

  useEffect(() => {
    if (!selectedMeeting || !isProcessingMeeting(selectedMeeting)) {
      return;
    }
    const meeting = selectedMeeting;
    const interval = window.setInterval(() => {
      void refreshSelectedMeetingState(meeting);
    }, 3000);
    return () => window.clearInterval(interval);
  }, [refreshSelectedMeetingState, selectedMeeting?.id, selectedMeeting?.status]);

  const submitMeeting = useCallback(() => {
    void run(async () => {
      const created = await createMeeting(token, draft.title, draft.language);
      setDraft({ title: "", language: draft.language });
      setMeetings((current) => [created, ...current]);
      selectMeeting(created.id);
      setLatestJob(null);
      setLastAsset(null);
      setIntelligenceResult(null);
      setNotice("Meeting created.");
    });
  }, [draft, run, selectMeeting, token]);

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
        await refreshAccountFiles();
      });
    },
    [lastAsset, refreshAccountFiles, refreshMeetings, run, selectedMeeting, token]
  );

  const uploadLibraryFile = useCallback(
    (file: File) => {
      void run(async () => {
        await uploadAccountFile(token, file);
        await refreshAccountFiles();
        setNotice("File stored.");
      });
    },
    [refreshAccountFiles, run, token]
  );

  const playLibraryFile = useCallback(
    (fileId: string) => {
      void run(async () => {
        const blob = await downloadAccountFile(token, fileId);
        setSelectedFileId(fileId);
        setFilePlaybackUrl((current) => {
          if (current) {
            URL.revokeObjectURL(current);
          }
          return URL.createObjectURL(blob);
        });
      });
    },
    [run, token]
  );

  const deleteLibraryFile = useCallback(
    (fileId: string) => {
      void run(async () => {
        await deleteAccountFile(token, fileId);
        if (selectedFileId === fileId && filePlaybackUrl) {
          URL.revokeObjectURL(filePlaybackUrl);
          setFilePlaybackUrl(null);
          setSelectedFileId(null);
        }
        await refreshAccountFiles();
        setNotice("File deleted.");
      });
    },
    [filePlaybackUrl, refreshAccountFiles, run, selectedFileId, token]
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
      const job = await queueMeetingProcessing(token, selectedMeeting.id, requestKey("process"));
      setLatestJob(job);
      setNotice(job.status === "FAILED" ? "Processing could not be queued." : "Processing queued.");
      await refreshMeetings();
    });
  }, [lastAsset, refreshMeetings, run, selectedMeeting, token]);

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
    const optimisticAnswer = createOptimisticChatMessage("assistant", CHAT_THINKING_TEXT);
    const submittedAfterMs = Date.now() - 10000;
    setChatQuestion("");
    setChatMessages((current) => [...current, optimisticQuestion, optimisticAnswer]);

    void run(async () => {
      let response;
      try {
        response = await askMeetingChat(
          token,
          selectedMeeting.id,
          question,
          selectedMeeting.language
        );
      } catch (caught) {
        if (!isNetworkLikeError(caught)) {
          setChatMessages((current) =>
            current.filter((item) => item.id !== optimisticQuestion.id && item.id !== optimisticAnswer.id)
          );
          throw caught;
        }

        let latestMessages: MeetingChatMessage[] = [];
        for (let attempt = 0; attempt < CHAT_RECOVERY_ATTEMPTS; attempt += 1) {
          if (attempt > 0) {
            await wait(CHAT_RECOVERY_DELAY_MS);
          }
          const history = await getMeetingChatHistory(token, selectedMeeting.id);
          latestMessages = history.messages;
          const recoveredAnswer = findAssistantAnswerAfterQuestion(history.messages, question, submittedAfterMs);
          if (recoveredAnswer) {
            const streamed = await streamAssistantMessage(optimisticAnswer.id, recoveredAnswer);
            if (streamed) {
              const latestHistory = await getMeetingChatHistory(token, selectedMeeting.id);
              setChatMessages(latestHistory.messages);
            }
            setNotice("Answer generated.");
            return;
          }
        }

        if (findQuestionMessageIndex(latestMessages, question, submittedAfterMs) >= 0) {
          setChatMessages((current) =>
            current.map((item) =>
              item.id === optimisticAnswer.id
                ? { ...item, content: "Câu hỏi đã được lưu. Câu trả lời vẫn đang được tạo, hãy refresh chat sau ít giây." }
                : item
            )
          );
          setNotice("Question saved. The answer is still generating; refresh chat in a moment.");
          return;
        }

        setChatMessages((current) =>
          current.filter((item) => item.id !== optimisticQuestion.id && item.id !== optimisticAnswer.id)
        );
        throw caught;
      }
      const streamed = await streamAssistantMessage(optimisticAnswer.id, response.message);
      if (!streamed) {
        return;
      }
      const history = await getMeetingChatHistory(token, selectedMeeting.id);
      setChatMessages(history.messages);
      setNotice(response.evidenceState === "not_enough_evidence" ? "No supported answer found." : "Answer generated.");
    });
  }, [chatQuestion, run, selectedMeeting, streamAssistantMessage, token]);

  const refreshChatHistory = useCallback(() => {
    if (!selectedMeeting) {
      return;
    }
    void run(async () => {
      const history = await getMeetingChatHistory(token, selectedMeeting.id);
      setChatMessages(history.messages);
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
      setLatestJob(null);
      setIntelligenceResult(null);
      await refreshAccountFiles();
      setNotice("Meeting session deleted.");
    });
  }, [refreshAccountFiles, run, selectMeeting, selectedMeeting, token]);

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

  useEffect(() => {
    return () => {
      if (filePlaybackUrl) {
        URL.revokeObjectURL(filePlaybackUrl);
      }
    };
  }, [filePlaybackUrl]);

  const canUpload = selectedMeeting ? isUploadableMeeting(selectedMeeting, lastAsset) : false;
  const canProcess = selectedMeeting ? isProcessableMeeting(selectedMeeting, lastAsset) : false;
  const hasLockedAsset = Boolean(lastAsset);

  return {
    accountFiles,
    assetPlaybackUrl,
    canProcess,
    canUpload,
    chatMessages,
    chatQuestion,
    draft,
    error,
    filePlaybackUrl,
    hasLockedAsset,
    intelligenceResult,
    isLoading,
    isRecording,
    lastAsset,
    latestJob,
    meetings,
    notice,
    selectedMeeting,
    selectedMeetingId,
    selectedFileId,
    queueProcessing,
    deleteLibraryFile,
    deleteSelectedMeeting,
    playLibraryFile,
    refreshChatHistory,
    refreshAccountFiles: () => void run(refreshAccountFiles),
    refreshMeetings: () => void run(refreshMeetings),
    refreshStatus,
    setChatQuestion,
    setDraft,
    setSelectedMeetingId: selectMeeting,
    startRecording,
    stopRecording,
    submitMeeting,
    submitChatQuestion,
    uploadFile,
    uploadLibraryFile
  };
}
