import { useCallback, useEffect, useRef, useState } from "react";
import { fixWebmDuration } from "@fix-webm-duration/fix";

import {
  buildRecordingFile,
  deleteRecordingSession,
  listRecordingSessions,
  recordingSessionId,
  saveRecordingChunk,
  saveRecordingSession,
} from "../api/recordingStorage";
import { isUploadableMeeting } from "../states/meetingState";
import type {
  Meeting,
  MeetingAsset,
  RecordingPhase,
  RecordingSession,
  StoredRecordingSession,
} from "../types/meetingTypes";
import { downloadBlob } from "../../../shared/utils/browserDownload";

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"] as const;

type UseMeetingRecordingArgs = {
  hasLoadedMeetings: boolean;
  lastAsset: MeetingAsset | null;
  meetings: Meeting[];
  onSelectMeeting: (meetingId: string) => void;
  ownerId: string;
  selectedMeeting: Meeting | null;
  setError: (message: string) => void;
  setNotice: (message: string) => void;
  uploadFileToMeeting: (meetingId: string, file: File) => Promise<MeetingAsset>;
};

function extensionForMimeType(mimeType: string): string {
  return mimeType.startsWith("audio/mp4") ? "m4a" : "webm";
}

function chooseMimeType(): { recorderMimeType: string; fileMimeType: string } {
  const recorderMimeType = MIME_CANDIDATES.find((candidate) => MediaRecorder.isTypeSupported(candidate));
  if (!recorderMimeType) {
    throw new Error("This browser does not support a compatible audio recording format.");
  }
  return {
    recorderMimeType,
    fileMimeType: recorderMimeType.startsWith("audio/webm") ? "audio/webm" : "audio/mp4",
  };
}

function storedSession(session: RecordingSession, phase: Exclude<RecordingPhase, "idle">, error: string | null): StoredRecordingSession {
  return {
    id: session.id,
    ownerId: session.ownerId,
    meetingId: session.meetingId,
    phase,
    mimeType: session.mimeType,
    fileName: session.fileName,
    startedAt: session.startedAt,
    updatedAt: Date.now(),
    durationMs: session.durationMs,
    chunkCount: session.chunkCount,
    uploadProgress: session.uploadProgress,
    isPartial: session.isPartial,
    error,
  };
}

async function prepareRecordingFile(file: File, session: RecordingSession): Promise<File> {
  if (file.type !== "audio/webm" || session.durationMs <= 0) return file;
  try {
    const fixed = await fixWebmDuration(file, session.durationMs, { logger: false });
    return new File([fixed], session.fileName, { type: "audio/webm", lastModified: Date.now() });
  } catch {
    // The Opus stream is still uploadable when metadata repair is unavailable.
    return file;
  }
}

export function useMeetingRecording({
  hasLoadedMeetings,
  lastAsset,
  meetings,
  onSelectMeeting,
  ownerId,
  selectedMeeting,
  setError,
  setNotice,
  uploadFileToMeeting,
}: UseMeetingRecordingArgs) {
  const [session, setSession] = useState<RecordingSession | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const sequenceRef = useRef(0);
  const writeQueueRef = useRef<Promise<void>>(Promise.resolve());
  const recoveryCheckedRef = useRef(false);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;
  }, []);

  const persistSession = useCallback(async (next: RecordingSession, phase: Exclude<RecordingPhase, "idle">, error: string | null = null) => {
    try {
      await saveRecordingSession(storedSession(next, phase, error));
    } catch {
      setSession((current) => current?.id === next.id
        ? { ...current, storageWarning: "Recording backup could not be saved. Keep this tab open until upload completes." }
        : current);
    }
  }, []);

  const uploadRecording = useCallback(async (activeSession: RecordingSession, file: File) => {
    const uploading: RecordingSession = { ...activeSession, phase: "uploading", file, uploadProgress: 0, updatedAt: Date.now(), error: null };
    setSession(uploading);
    await persistSession(uploading, "uploading");
    try {
      await uploadFileToMeeting(activeSession.meetingId, file);
      await deleteRecordingSession(activeSession.id).catch(() => undefined);
      setSession(null);
      chunksRef.current = [];
      sequenceRef.current = 0;
      setNotice("Recording uploaded.");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Recording upload failed.";
      const failed: RecordingSession = { ...uploading, phase: "failed", uploadProgress: null, error: message, updatedAt: Date.now() };
      setSession(failed);
      await persistSession(failed, "failed", message);
      setError(`${message} Your recording was kept for retry.`);
    }
  }, [persistSession, setError, setNotice, uploadFileToMeeting]);

  const finalizeRecording = useCallback(async (activeSession: RecordingSession) => {
    const finalizing: RecordingSession = { ...activeSession, phase: "finalizing", updatedAt: Date.now() };
    setSession(finalizing);
    await persistSession(finalizing, "finalizing");
    await writeQueueRef.current;
    let file: File;
    try {
      file = await buildRecordingFile(storedSession(finalizing, "finalizing", null));
    } catch {
      if (chunksRef.current.length === 0) {
        const failed = { ...finalizing, phase: "failed" as const, error: "The recording contains no audio data." };
        setSession(failed);
        await persistSession(failed, "failed", failed.error);
        setError(failed.error);
        return;
      }
      file = new File(chunksRef.current, finalizing.fileName, { type: finalizing.mimeType });
    }
    file = await prepareRecordingFile(file, finalizing);
    await uploadRecording(finalizing, file);
  }, [persistSession, setError, uploadRecording]);

  const startRecording = useCallback(() => {
    if (!selectedMeeting) {
      setError("Select a meeting first.");
      return;
    }
    if (session) {
      setError("Resolve the current recording before starting another one.");
      return;
    }
    if (!isUploadableMeeting(selectedMeeting, lastAsset)) {
      setError("This meeting already has an uploaded file or processing output. Create a new meeting to record another file.");
      return;
    }

    const meetingId = selectedMeeting.id;
    let recorderMimeType: string;
    let mimeType: string;
    try {
      ({ recorderMimeType, fileMimeType: mimeType } = chooseMimeType());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Recording is unavailable.");
      return;
    }
    const startedAt = Date.now();
    const requesting: RecordingSession = {
      id: recordingSessionId(ownerId, meetingId),
      ownerId,
      meetingId,
      phase: "requesting_permission",
      mimeType,
      fileName: `recording-${new Date(startedAt).toISOString()}.${extensionForMimeType(mimeType)}`,
      startedAt,
      updatedAt: startedAt,
      durationMs: 0,
      chunkCount: 0,
      uploadProgress: null,
      isPartial: false,
      error: null,
      file: null,
      storageWarning: null,
    };
    setSession(requesting);
    void persistSession(requesting, "requesting_permission");

    void navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream, { mimeType: recorderMimeType });
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];
      sequenceRef.current = 0;
      writeQueueRef.current = Promise.resolve();
      const recording: RecordingSession = { ...requesting, phase: "recording", updatedAt: Date.now() };
      setSession(recording);
      void persistSession(recording, "recording");

      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size === 0) return;
        const sequence = sequenceRef.current++;
        chunksRef.current.push(event.data);
        recording.chunkCount = sequence + 1;
        recording.updatedAt = Date.now();
        recording.durationMs = recording.updatedAt - recording.startedAt;
        setSession((current) => current?.id === recording.id ? { ...current, chunkCount: sequence + 1, durationMs: recording.durationMs, updatedAt: recording.updatedAt } : current);
        writeQueueRef.current = writeQueueRef.current
          .then(async () => saveRecordingChunk({ sessionId: recording.id, sequence, data: await event.data.arrayBuffer(), createdAt: Date.now() }))
          .then(() => saveRecordingSession(storedSession(recording, "recording", null)))
          .catch(() => {
            setSession((current) => current?.id === recording.id
              ? { ...current, storageWarning: "Recording backup could not be saved. Keep this tab open until upload completes." }
              : current);
          });
      });
      recorder.addEventListener("stop", () => {
        stopStream();
        const stoppedAt = Date.now();
        void finalizeRecording({ ...recording, chunkCount: sequenceRef.current, durationMs: stoppedAt - recording.startedAt, updatedAt: stoppedAt });
      }, { once: true });
      recorder.addEventListener("error", () => {
        stopStream();
        const failed = { ...recording, phase: "failed" as const, error: "Audio recording failed.", chunkCount: sequenceRef.current, updatedAt: Date.now() };
        setSession(failed);
        void persistSession(failed, "failed", failed.error);
        setError(failed.error);
      }, { once: true });
      recorder.start(1000);
      setNotice("Recording started.");
    }).catch((caught) => {
      stopStream();
      void deleteRecordingSession(requesting.id).catch(() => undefined);
      setSession(null);
      setError(caught instanceof Error ? caught.message : "Microphone permission was denied.");
    });
  }, [lastAsset, ownerId, persistSession, selectedMeeting, session, setError, setNotice, stopStream, finalizeRecording]);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    setSession((current) => current ? { ...current, phase: "finalizing", updatedAt: Date.now() } : current);
    recorder.stop();
    setNotice("Recording stopped. Finalizing audio…");
  }, [setNotice]);

  const retryUpload = useCallback(() => {
    if (!session || (session.phase !== "failed" && session.phase !== "recoverable")) return;
    void (async () => {
      try {
        const rawFile = session.file ?? await buildRecordingFile(storedSession(session, session.phase, session.error));
        const file = await prepareRecordingFile(rawFile, session);
        await uploadRecording(session, file);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "The recording could not be recovered.");
      }
    })();
  }, [session, setError, uploadRecording]);

  const downloadRecording = useCallback(() => {
    if (!session) return;
    void (async () => {
      try {
        const rawFile = session.file ?? await buildRecordingFile(storedSession(session, session.phase, session.error));
        const file = await prepareRecordingFile(rawFile, session);
        downloadBlob(file, session.fileName);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "The recording could not be downloaded.");
      }
    })();
  }, [session, setError]);

  const discardRecording = useCallback(() => {
    if (!session || session.phase === "recording" || session.phase === "requesting_permission" || session.phase === "finalizing" || session.phase === "uploading") return;
    void deleteRecordingSession(session.id).catch(() => undefined);
    setSession(null);
    chunksRef.current = [];
    sequenceRef.current = 0;
    setNotice("Saved recording discarded.");
  }, [session, setNotice]);

  useEffect(() => {
    if (!hasLoadedMeetings || recoveryCheckedRef.current || session) return;
    recoveryCheckedRef.current = true;
    void (async () => {
      try {
        const savedSessions = await listRecordingSessions(ownerId);
        for (const saved of savedSessions) {
          const meeting = meetings.find((item) => item.id === saved.meetingId);
          if (meeting && meeting.status !== "DRAFT") {
            await deleteRecordingSession(saved.id);
            continue;
          }
          const recovered: RecordingSession = {
            ...saved,
            phase: "recoverable",
            isPartial: saved.phase === "recording" || saved.phase === "requesting_permission",
            durationMs: saved.durationMs || Math.max(0, saved.updatedAt - saved.startedAt),
            uploadProgress: null,
            error: saved.error,
            file: null,
            storageWarning: null,
            updatedAt: Date.now(),
          };
          setSession(recovered);
          await persistSession(recovered, "recoverable", saved.error);
          if (meeting) onSelectMeeting(meeting.id);
          setNotice(recovered.isPartial ? "A partial recording was recovered." : "A recording is ready to retry.");
          break;
        }
      } catch {
        setError("Saved recordings could not be checked in this browser.");
      }
    })();
  }, [hasLoadedMeetings, meetings, onSelectMeeting, ownerId, persistSession, session, setError, setNotice]);

  useEffect(() => {
    if (!session) return;
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [session]);

  useEffect(() => () => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    stopStream();
  }, [stopStream]);

  return {
    session,
    isLocked: session !== null,
    isRecording: session?.phase === "recording",
    lockedMeetingId: session?.meetingId ?? null,
    discardRecording,
    downloadRecording,
    retryUpload,
    startRecording,
    stopRecording,
  };
}
