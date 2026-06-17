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

function requestKey(prefix: string) {
  return `${prefix}:${crypto.randomUUID()}`;
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

export function useMeetingWorkspace(token: string, isAdmin: boolean) {
  const [draft, setDraft] = useState<MeetingDraft>({ title: "", language: "vi" });
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [accountFiles, setAccountFiles] = useState<AccountFile[]>([]);
  const [filePlaybackUrl, setFilePlaybackUrl] = useState<string | null>(null);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);
  const [latestJob, setLatestJob] = useState<ProcessingJob | null>(null);
  const [lastAsset, setLastAsset] = useState<MeetingAsset | null>(null);
  const [assetPlaybackUrl, setAssetPlaybackUrl] = useState<string | null>(null);
  const [intelligenceResult, setIntelligenceResult] = useState<MeetingIntelligenceResult | null>(null);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<MeetingChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingChunksRef = useRef<BlobPart[]>([]);

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

  const refreshMeetings = useCallback(async () => {
    const nextMeetings = await listMeetings(token);
    setMeetings(nextMeetings);
    setSelectedMeetingId((current) => current ?? nextMeetings[0]?.id ?? null);
  }, [token]);

  const refreshAccountFiles = useCallback(async () => {
    setAccountFiles(await listAccountFiles(token));
  }, [token]);

  useEffect(() => {
    void run(refreshMeetings);
    void run(refreshAccountFiles);
  }, [refreshAccountFiles, refreshMeetings, run]);

  useEffect(() => {
    setChatQuestion("");
    setChatSessionId(null);
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
      } else {
        setIntelligenceResult(null);
      }
    },
    [token]
  );

  useEffect(() => {
    if (!selectedMeeting) {
      return;
    }
    const meeting = selectedMeeting;
    void run(async () => {
      await refreshSelectedMeetingState(meeting);
    });
  }, [refreshSelectedMeetingState, run, selectedMeetingId]);

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
      setSelectedMeetingId(created.id);
      setLatestJob(null);
      setLastAsset(null);
      setIntelligenceResult(null);
      setNotice("Meeting created.");
    });
  }, [draft, run, token]);

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
    void run(async () => {
      const response = await askMeetingChat(
        token,
        selectedMeeting.id,
        question,
        chatSessionId,
        selectedMeeting.language
      );
      setChatSessionId(response.sessionId);
      setChatQuestion("");
      const history = await getMeetingChatHistory(token, selectedMeeting.id, response.sessionId);
      setChatMessages(history.messages);
      setNotice(response.evidenceState === "not_enough_evidence" ? "No supported answer found." : "Answer generated.");
    });
  }, [chatQuestion, chatSessionId, run, selectedMeeting, token]);

  const refreshChatHistory = useCallback(() => {
    if (!selectedMeeting || !chatSessionId) {
      return;
    }
    void run(async () => {
      const history = await getMeetingChatHistory(token, selectedMeeting.id, chatSessionId);
      setChatMessages(history.messages);
      setNotice("Chat refreshed.");
    });
  }, [chatSessionId, run, selectedMeeting, token]);

  const deleteSelectedMeeting = useCallback(() => {
    if (!selectedMeeting || !isAdmin) {
      setError("Admin access is required to delete a meeting session.");
      return;
    }
    void run(async () => {
      await deleteMeetingSession(token, selectedMeeting.id);
      setMeetings((current) => current.filter((item) => item.id !== selectedMeeting.id));
      setSelectedMeetingId(null);
      setLastAsset(null);
      setLatestJob(null);
      setIntelligenceResult(null);
      await refreshAccountFiles();
      setNotice("Meeting session deleted.");
    });
  }, [isAdmin, refreshAccountFiles, run, selectedMeeting, token]);

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
    chatSessionId,
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
    setSelectedMeetingId,
    startRecording,
    stopRecording,
    submitMeeting,
    submitChatQuestion,
    uploadFile,
    uploadLibraryFile
  };
}
