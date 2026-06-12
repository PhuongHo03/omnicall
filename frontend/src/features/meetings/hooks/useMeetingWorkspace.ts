import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  askMeetingChat,
  createMeeting,
  getMeetingChatHistory,
  getProcessingStatus,
  listMeetings,
  queueMeetingProcessing,
  uploadMeetingAsset
} from "../api/meetingApi";
import type {
  DevAuthContext,
  Meeting,
  MeetingAsset,
  MeetingChatMessage,
  MeetingDraft,
  ProcessingJob
} from "../types/meetingTypes";

const DEFAULT_CONTEXT: DevAuthContext = {
  userId: "11111111-1111-4111-8111-111111111111",
  workspaceId: "22222222-2222-4222-8222-222222222222",
  userEmail: "local@omnicall.test",
  userName: "Local Operator",
  workspaceName: "Local Workspace"
};

function requestKey(prefix: string) {
  return `${prefix}:${crypto.randomUUID()}`;
}

export function useMeetingWorkspace() {
  const [authContext, setAuthContext] = useState<DevAuthContext>(DEFAULT_CONTEXT);
  const [draft, setDraft] = useState<MeetingDraft>({ title: "", language: "vi" });
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);
  const [latestJob, setLatestJob] = useState<ProcessingJob | null>(null);
  const [lastAsset, setLastAsset] = useState<MeetingAsset | null>(null);
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
    const nextMeetings = await listMeetings(authContext);
    setMeetings(nextMeetings);
    setSelectedMeetingId((current) => current ?? nextMeetings[0]?.id ?? null);
  }, [authContext]);

  useEffect(() => {
    void run(refreshMeetings);
  }, [refreshMeetings, run]);

  useEffect(() => {
    setChatQuestion("");
    setChatSessionId(null);
    setChatMessages([]);
  }, [selectedMeetingId]);

  const submitMeeting = useCallback(() => {
    void run(async () => {
      const created = await createMeeting(authContext, draft.title, draft.language);
      setDraft({ title: "", language: draft.language });
      setMeetings((current) => [created, ...current]);
      setSelectedMeetingId(created.id);
      setLatestJob(null);
      setLastAsset(null);
      setNotice("Meeting created.");
    });
  }, [authContext, draft, run]);

  const uploadFile = useCallback(
    (file: File) => {
      if (!selectedMeeting) {
        setError("Select a meeting first.");
        return;
      }
      void run(async () => {
        const asset = await uploadMeetingAsset(authContext, selectedMeeting.id, file, requestKey("upload"));
        setLastAsset(asset);
        setNotice("Upload completed.");
        await refreshMeetings();
      });
    },
    [authContext, refreshMeetings, run, selectedMeeting]
  );

  const queueProcessing = useCallback(() => {
    if (!selectedMeeting) {
      setError("Select a meeting first.");
      return;
    }
    void run(async () => {
      const job = await queueMeetingProcessing(authContext, selectedMeeting.id, requestKey("process"));
      setLatestJob(job);
      setNotice(job.status === "FAILED" ? "Processing could not be queued." : "Processing queued.");
      await refreshMeetings();
    });
  }, [authContext, refreshMeetings, run, selectedMeeting]);

  const refreshStatus = useCallback(() => {
    if (!selectedMeeting) {
      setError("Select a meeting first.");
      return;
    }
    void run(async () => {
      const status = await getProcessingStatus(authContext, selectedMeeting.id);
      setMeetings((current) => current.map((meeting) => (meeting.id === status.meeting.id ? status.meeting : meeting)));
      setLatestJob(status.latestJob);
      setNotice("Status refreshed.");
    });
  }, [authContext, run, selectedMeeting]);

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
        authContext,
        selectedMeeting.id,
        question,
        chatSessionId,
        selectedMeeting.language
      );
      setChatSessionId(response.sessionId);
      setChatQuestion("");
      const history = await getMeetingChatHistory(authContext, selectedMeeting.id, response.sessionId);
      setChatMessages(history.messages);
      setNotice(response.evidenceState === "not_enough_evidence" ? "No supported answer found." : "Answer generated.");
    });
  }, [authContext, chatQuestion, chatSessionId, run, selectedMeeting]);

  const refreshChatHistory = useCallback(() => {
    if (!selectedMeeting || !chatSessionId) {
      return;
    }
    void run(async () => {
      const history = await getMeetingChatHistory(authContext, selectedMeeting.id, chatSessionId);
      setChatMessages(history.messages);
      setNotice("Chat refreshed.");
    });
  }, [authContext, chatSessionId, run, selectedMeeting]);

  const startRecording = useCallback(() => {
    if (!selectedMeeting) {
      setError("Select a meeting first.");
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
  }, [run, selectedMeeting, uploadFile]);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
      setIsRecording(false);
      setNotice("Recording stopped.");
    }
  }, []);

  return {
    authContext,
    chatMessages,
    chatQuestion,
    chatSessionId,
    draft,
    error,
    isLoading,
    isRecording,
    lastAsset,
    latestJob,
    meetings,
    notice,
    selectedMeeting,
    selectedMeetingId,
    queueProcessing,
    refreshChatHistory,
    refreshMeetings: () => void run(refreshMeetings),
    refreshStatus,
    setAuthContext,
    setChatQuestion,
    setDraft,
    setSelectedMeetingId,
    startRecording,
    stopRecording,
    submitMeeting,
    submitChatQuestion,
    uploadFile
  };
}
