import { useCallback, useRef, useState } from "react";

import { isUploadableMeeting } from "../states/meetingState";
import type { Meeting, MeetingAsset } from "../types/meetingTypes";

type UseMeetingRecordingArgs = {
  lastAsset: MeetingAsset | null;
  run: (operation: () => Promise<void>) => Promise<void>;
  selectedMeeting: Meeting | null;
  setError: (message: string) => void;
  setNotice: (message: string) => void;
  uploadFile: (file: File) => void;
};

export function useMeetingRecording({
  lastAsset,
  run,
  selectedMeeting,
  setError,
  setNotice,
  uploadFile,
}: UseMeetingRecordingArgs) {
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingChunksRef = useRef<BlobPart[]>([]);

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
  }, [lastAsset, run, selectedMeeting, setError, setNotice, uploadFile]);

  const stopRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
      setIsRecording(false);
      setNotice("Recording stopped.");
    }
  }, [setNotice]);

  return {
    isRecording,
    startRecording,
    stopRecording,
  };
}
