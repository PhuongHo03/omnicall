import { act, renderHook, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setChatFeedback } from "../api/meetingApi";
import { useChatFeedback } from "../hooks/useChatFeedback";
import type { ChatFeedbackResult, MeetingChatMessage } from "../types/meetingTypes";

vi.mock("../api/meetingApi", () => ({
  setChatFeedback: vi.fn(),
}));

const setChatFeedbackMock = vi.mocked(setChatFeedback);

function message(overrides: Partial<MeetingChatMessage> = {}): MeetingChatMessage {
  return {
    id: "message-1",
    role: "assistant",
    content: "Grounded answer",
    retrievedChunkIds: ["chunk-1"],
    citations: [],
    metadata: { evidenceState: "grounded", feedbackEligible: true },
    feedbackRating: "up",
    feedbackRevision: 2,
    feedbackStatus: "active",
    feedbackCacheAction: "none",
    createdAt: "2026-07-15T00:00:00Z",
    ...overrides,
  };
}

function useHarness(onError: (message: string) => void) {
  const [messages, setMessages] = useState([message()]);
  const feedback = useChatFeedback({
    meetingId: "meeting-1",
    messages,
    onError,
    setMessages,
    token: "token",
  });
  return { ...feedback, messages };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, reject, resolve };
}

describe("useChatFeedback", () => {
  beforeEach(() => {
    setChatFeedbackMock.mockReset();
  });

  it("applies the authoritative response and tracks per-message pending state", async () => {
    const request = deferred<ChatFeedbackResult>();
    setChatFeedbackMock.mockReturnValue(request.promise);
    const { result } = renderHook(() => useHarness(vi.fn()));

    act(() => result.current.submitChatFeedback("message-1", "down"));
    expect(result.current.messages[0].feedbackRating).toBe("down");
    expect(result.current.pendingFeedbackMessageIds.has("message-1")).toBe(true);
    expect(setChatFeedbackMock).toHaveBeenCalledWith("token", "meeting-1", "message-1", "down", 2);

    act(() => request.resolve({
      messageId: "message-1",
      rating: "down",
      revision: 3,
      status: "inactive",
      cacheAction: "invalidated",
    }));
    await waitFor(() => expect(result.current.pendingFeedbackMessageIds.has("message-1")).toBe(false));
    expect(result.current.messages[0]).toMatchObject({
      feedbackRating: "down",
      feedbackRevision: 3,
      feedbackStatus: "inactive",
      feedbackCacheAction: "invalidated",
    });
  });

  it("rolls back only the latest failed intent", async () => {
    const onError = vi.fn();
    setChatFeedbackMock.mockRejectedValue(new Error("Feedback unavailable"));
    const { result } = renderHook(() => useHarness(onError));

    act(() => result.current.submitChatFeedback("message-1", "neutral"));
    expect(result.current.messages[0].feedbackRating).toBeNull();
    await waitFor(() => expect(onError).toHaveBeenCalledWith("Feedback unavailable"));
    expect(result.current.messages[0]).toMatchObject({
      feedbackRating: "up",
      feedbackRevision: 2,
      feedbackStatus: "active",
    });
  });

  it("ignores rapid repeat intents while the message request is pending", async () => {
    const first = deferred<ChatFeedbackResult>();
    setChatFeedbackMock.mockReturnValue(first.promise);
    const { result } = renderHook(() => useHarness(vi.fn()));

    act(() => result.current.submitChatFeedback("message-1", "neutral"));
    act(() => result.current.submitChatFeedback("message-1", "down"));
    expect(setChatFeedbackMock).toHaveBeenCalledTimes(1);

    act(() => first.resolve({
      messageId: "message-1",
      rating: "neutral",
      revision: 3,
      status: "removed",
      cacheAction: "none",
    }));
    await waitFor(() => expect(result.current.messages[0].feedbackRevision).toBe(3));
    expect(result.current.messages[0].feedbackRating).toBeNull();
  });

  it("does not let stale history or rollback overwrite a newer feedback revision", async () => {
    const onError = vi.fn();
    const request = deferred<ChatFeedbackResult>();
    setChatFeedbackMock.mockReturnValue(request.promise);
    const { result } = renderHook(() => useHarness(onError));

    act(() => result.current.submitChatFeedback("message-1", "down"));
    act(() => result.current.applyChatHistory([
      message({ feedbackRating: null, feedbackRevision: 1, feedbackStatus: "removed" }),
    ]));
    expect(result.current.messages[0]).toMatchObject({
      feedbackRating: "down",
      feedbackRevision: 2,
      feedbackStatus: "pending",
    });

    act(() => result.current.applyChatHistory([
      message({ feedbackRating: "up", feedbackRevision: 3, feedbackStatus: "active" }),
    ]));
    act(() => request.reject(new Error("Feedback revision changed")));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Feedback revision changed"));
    expect(result.current.messages[0]).toMatchObject({
      feedbackRating: "up",
      feedbackRevision: 3,
      feedbackStatus: "active",
    });
  });
});
