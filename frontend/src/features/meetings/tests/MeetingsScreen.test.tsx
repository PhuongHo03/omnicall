import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useMeetingWorkspace } from "../hooks/useMeetingWorkspace";
import { MeetingsScreen } from "../screens/MeetingsScreen";
import type { MeetingChatMessage } from "../types/meetingTypes";

vi.mock("../hooks/useMeetingWorkspace", () => ({
  useMeetingWorkspace: vi.fn(),
}));

vi.mock("../../../shared/layouts/SidebarContext", () => ({
  useSidebarSlot: () => ({
    setCreateMeetingDisabled: vi.fn(),
    setExtraContent: vi.fn(),
    setOnCreateMeeting: vi.fn(),
  }),
}));

const useMeetingWorkspaceMock = vi.mocked(useMeetingWorkspace);

function assistantMessage(pending: boolean): MeetingChatMessage {
  return {
    id: pending ? "local:assistant" : "assistant-1",
    role: "assistant",
    content: pending ? "Đang xử lý..." : "Grounded answer",
    retrievedChunkIds: pending ? [] : ["chunk-1"],
    citations: [],
    metadata: pending
      ? { local: true, pending: true }
      : { evidenceState: "grounded", feedbackEligible: true },
    feedbackRating: pending ? null : "up",
    feedbackRevision: pending ? 0 : 3,
    createdAt: "2026-07-15T00:00:00Z",
  };
}

function workspaceFixture(overrides: Record<string, unknown> = {}) {
  const noop = vi.fn();
  return {
    assetPlaybackError: null,
    assetPlaybackStatus: "idle",
    assetPlaybackUrl: null,
    canProcess: false,
    canUpload: false,
    chatMessages: [assistantMessage(true)],
    chatQuestion: "Ai là khách hàng?",
    clearTypewriterId: noop,
    createNewMeeting: noop,
    deleteSelectedMeeting: noop,
    discardRecording: noop,
    downloadAsset: noop,
    downloadRecording: noop,
    intelligenceResult: {},
    isLoading: false,
    isOperationLocked: false,
    isRecording: false,
    recordingSession: null,
    lastAsset: null,
    meetings: [],
    pendingFeedbackMessageIds: new Set<string>(),
    queueProcessing: noop,
    refreshChatHistory: noop,
    refreshStatus: noop,
    retryRecordingUpload: noop,
    renameSelectedMeeting: noop,
    selectedMeeting: {
      id: "meeting-1",
      title: "Sales call",
      status: "READY",
      failureCode: null,
      failureReason: null,
      pendingChatStatus: "started",
      createdAt: "2026-07-15T00:00:00Z",
      updatedAt: "2026-07-15T00:00:00Z",
      latestAsset: null,
      retryAllowed: false,
    },
    selectedMeetingId: "meeting-1",
    setChatQuestion: noop,
    setSelectedMeetingId: noop,
    startRecording: noop,
    stopRecording: noop,
    submitChatFeedback: noop,
    submitChatQuestion: noop,
    transcriptEntries: [],
    typewriterMessageIds: new Set<string>(),
    uploadFile: noop,
    uploadProgress: null,
    ...overrides,
  } as unknown as ReturnType<typeof useMeetingWorkspace>;
}

describe("MeetingsScreen", () => {
  beforeEach(() => {
    useMeetingWorkspaceMock.mockReset();
  });

  it("preserves the disabled question draft while another answer is pending", () => {
    useMeetingWorkspaceMock.mockReturnValue(workspaceFixture());

    render(<MeetingsScreen requestedMeetingId="meeting-1" token="token" userId="user-1" onSelectedMeetingChange={vi.fn()} />);

    expect(screen.getByRole("textbox")).toHaveValue("Ai là khách hàng?");
    expect(screen.getByRole("textbox")).toBeDisabled();
  });

  it("renders persisted selected feedback", () => {
    useMeetingWorkspaceMock.mockReturnValue(workspaceFixture({
      chatMessages: [assistantMessage(false)],
    }));

    render(<MeetingsScreen requestedMeetingId="meeting-1" token="token" userId="user-1" onSelectedMeetingChange={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Remove helpful feedback" })).toHaveAttribute("aria-pressed", "true");
  });

  it("refreshes authoritative meeting state without launching a second chat refresh", () => {
    const refreshStatus = vi.fn();
    const refreshChatHistory = vi.fn();
    useMeetingWorkspaceMock.mockReturnValue(workspaceFixture({ refreshStatus, refreshChatHistory }));

    render(<MeetingsScreen requestedMeetingId="meeting-1" token="token" userId="user-1" onSelectedMeetingChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(refreshStatus).toHaveBeenCalledOnce();
    expect(refreshChatHistory).not.toHaveBeenCalled();
  });

  it("keeps upload visible but disables meeting actions while recording", () => {
    useMeetingWorkspaceMock.mockReturnValue(workspaceFixture({
      canUpload: true,
      isOperationLocked: true,
      isRecording: true,
      intelligenceResult: null,
      recordingSession: {
        id: "user-1:meeting-1",
        ownerId: "user-1",
        meetingId: "meeting-1",
        phase: "recording",
        mimeType: "audio/webm",
        fileName: "recording.webm",
        startedAt: 1,
        updatedAt: 1,
        durationMs: 1000,
        chunkCount: 1,
        uploadProgress: null,
        isPartial: false,
        error: null,
        file: null,
        storageWarning: null,
      },
      selectedMeeting: {
        id: "meeting-1",
        title: "Draft call",
        status: "DRAFT",
        failureCode: null,
        failureReason: null,
        pendingChatStatus: null,
        createdAt: "2026-07-15T00:00:00Z",
        updatedAt: "2026-07-15T00:00:00Z",
        latestAsset: null,
        retryAllowed: false,
      },
    }));

    render(<MeetingsScreen requestedMeetingId="meeting-1" token="token" userId="user-1" onSelectedMeetingChange={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(screen.getByText("Đang ghi âm…")).toBeInTheDocument();
  });

  it("shows a Vietnamese no-speech message without exposing the English backend reason", () => {
    useMeetingWorkspaceMock.mockReturnValue(workspaceFixture({
      selectedMeeting: {
        ...workspaceFixture().selectedMeeting,
        status: "FAILED",
        failureCode: "NO_RECOGNIZABLE_SPEECH",
        failureReason: "No clear speech was detected in this recording.",
        retryAllowed: true,
      },
    }));

    render(<MeetingsScreen requestedMeetingId="meeting-1" token="token" userId="user-1" onSelectedMeetingChange={vi.fn()} />);

    expect(screen.getByText("Không phát hiện lời nói rõ ràng")).toBeInTheDocument();
    expect(screen.getByText(/Bản ghi vẫn có thể nghe lại hoặc tải xuống/)).toBeInTheDocument();
    expect(screen.queryByText("No clear speech was detected in this recording.")).not.toBeInTheDocument();
  });
});
