import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildRecordingFile,
  deleteRecordingSession,
  listRecordingSessions,
  saveRecordingChunk,
  saveRecordingSession,
} from "../api/recordingStorage";
import { useMeetingRecording } from "../hooks/useMeetingRecording";
import type { Meeting, MeetingAsset } from "../types/meetingTypes";
import { fixWebmDuration } from "@fix-webm-duration/fix";

vi.mock("@fix-webm-duration/fix", () => ({ fixWebmDuration: vi.fn() }));

vi.mock("../api/recordingStorage", () => ({
  buildRecordingFile: vi.fn(),
  deleteRecordingSession: vi.fn(),
  listRecordingSessions: vi.fn(),
  recordingSessionId: (ownerId: string, meetingId: string) => `${ownerId}:${meetingId}`,
  saveRecordingChunk: vi.fn(),
  saveRecordingSession: vi.fn(),
}));

class FakeMediaRecorder extends EventTarget {
  static instances: FakeMediaRecorder[] = [];
  static isTypeSupported(type: string) {
    return type === "audio/webm;codecs=opus";
  }

  readonly mimeType: string;
  state: RecordingState = "inactive";
  startTimeslice: number | undefined;

  constructor(_stream: MediaStream, options?: MediaRecorderOptions) {
    super();
    this.mimeType = options?.mimeType ?? "";
    FakeMediaRecorder.instances.push(this);
  }

  start(timeslice?: number) {
    this.state = "recording";
    this.startTimeslice = timeslice;
  }

  stop() {
    const event = new Event("dataavailable") as BlobEvent;
    Object.defineProperty(event, "data", { value: new Blob(["audio"], { type: this.mimeType }) });
    this.dispatchEvent(event);
    this.state = "inactive";
    this.dispatchEvent(new Event("stop"));
  }
}

const meeting: Meeting = {
  id: "meeting-1",
  title: "Draft call",
    status: "DRAFT",
    failureCode: null,
    failureReason: null,
  pendingChatStatus: null,
  createdAt: "2026-07-16T00:00:00Z",
  updatedAt: "2026-07-16T00:00:00Z",
  latestAsset: null,
  retryAllowed: false,
};

const asset: MeetingAsset = {
  id: "asset-1",
  meetingId: "meeting-1",
  objectKey: "recording.webm",
  fileName: "recording.webm",
  contentType: "audio/webm",
  sizeBytes: 5,
  createdAt: "2026-07-16T00:00:01Z",
};

describe("useMeetingRecording", () => {
  const trackStop = vi.fn();
  const uploadFileToMeeting = vi.fn();

  beforeEach(() => {
    FakeMediaRecorder.instances = [];
    trackStop.mockReset();
    uploadFileToMeeting.mockReset();
    vi.mocked(buildRecordingFile).mockReset();
    vi.mocked(deleteRecordingSession).mockReset().mockResolvedValue(undefined);
    vi.mocked(listRecordingSessions).mockReset().mockResolvedValue([]);
    vi.mocked(saveRecordingChunk).mockReset().mockResolvedValue(undefined);
    vi.mocked(saveRecordingSession).mockReset().mockResolvedValue(undefined);
    vi.mocked(buildRecordingFile).mockResolvedValue(new File(["audio"], "recording.webm", { type: "audio/webm" }));
    vi.mocked(fixWebmDuration).mockReset().mockResolvedValue(new Blob(["fixed-audio"], { type: "audio/webm" }));
    Object.defineProperty(globalThis, "MediaRecorder", { configurable: true, value: FakeMediaRecorder });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: trackStop }] }) },
    });
  });

  function renderRecording() {
    return renderHook(() => useMeetingRecording({
      hasLoadedMeetings: false,
      lastAsset: null,
      meetings: [meeting],
      onSelectMeeting: vi.fn(),
      ownerId: "user-1",
      selectedMeeting: meeting,
      setError: vi.fn(),
      setNotice: vi.fn(),
      uploadFileToMeeting,
    }));
  }

  it("persists timed chunks and uploads the finalized file to the recording owner meeting", async () => {
    uploadFileToMeeting.mockResolvedValue(asset);
    const { result } = renderRecording();

    act(() => result.current.startRecording());
    await waitFor(() => expect(result.current.session?.phase).toBe("recording"));
    expect(FakeMediaRecorder.instances[0].mimeType).toBe("audio/webm;codecs=opus");
    expect(FakeMediaRecorder.instances[0].startTimeslice).toBe(1000);

    act(() => result.current.stopRecording());
    await waitFor(() => expect(uploadFileToMeeting).toHaveBeenCalledWith("meeting-1", expect.any(File)));
    expect(uploadFileToMeeting.mock.calls[0][1].type).toBe("audio/webm");
    expect(fixWebmDuration).toHaveBeenCalledWith(expect.any(Blob), expect.any(Number), { logger: false });
    await waitFor(() => expect(result.current.session).toBeNull());
    expect(saveRecordingChunk).toHaveBeenCalledWith(expect.objectContaining({ sessionId: "user-1:meeting-1", sequence: 0 }));
    expect(deleteRecordingSession).toHaveBeenCalledWith("user-1:meeting-1");
    expect(trackStop).toHaveBeenCalledOnce();
  });

  it("keeps a failed recording and retries the same meeting", async () => {
    uploadFileToMeeting.mockRejectedValueOnce(new Error("Offline"));
    const { result } = renderRecording();

    act(() => result.current.startRecording());
    await waitFor(() => expect(result.current.session?.phase).toBe("recording"));
    act(() => result.current.stopRecording());
    await waitFor(() => expect(result.current.session?.phase).toBe("failed"));

    uploadFileToMeeting.mockResolvedValueOnce(asset);
    act(() => result.current.retryUpload());
    await waitFor(() => expect(result.current.session).toBeNull());
    expect(uploadFileToMeeting).toHaveBeenNthCalledWith(2, "meeting-1", expect.any(File));
  });
});
