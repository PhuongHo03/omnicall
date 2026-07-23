import { describe, expect, it } from "vitest";

import {
  mergeChatHistory,
  restoreRejectedChatQuestion,
  toggledFeedbackSelection,
} from "../states/chatState";
import type { MeetingChatMessage } from "../types/meetingTypes";

function message(
  feedbackRating: MeetingChatMessage["feedbackRating"],
  feedbackRevision: number,
  feedbackStatus?: MeetingChatMessage["feedbackStatus"],
): MeetingChatMessage {
  return {
    id: "assistant-1",
    role: "assistant",
    content: "Grounded answer",
    retrievedChunkIds: ["chunk-1"],
    citations: [],
    metadata: { evidenceState: "grounded", feedbackEligible: true },
    feedbackRating,
    feedbackRevision,
    feedbackStatus,
    createdAt: "2026-07-15T00:00:00Z",
  };
}

describe("chat state transitions", () => {
  it("restores a submitted question after chat_busy without overwriting a newer draft", () => {
    expect(restoreRejectedChatQuestion("", "Ai là khách hàng?")).toBe("Ai là khách hàng?");
    expect(restoreRejectedChatQuestion("Câu hỏi mới", "Ai là khách hàng?")).toBe("Câu hỏi mới");
  });

  it("toggles an active feedback rating back to neutral", () => {
    expect(toggledFeedbackSelection("up", "up")).toBe("neutral");
    expect(toggledFeedbackSelection("down", "up")).toBe("up");
  });

  it("preserves pending feedback and the highest revision against stale history", () => {
    const optimistic = message("down", 4, "pending");
    const stale = message("up", 3, "active");

    expect(mergeChatHistory([optimistic], [stale], new Set(["assistant-1"]))[0]).toMatchObject({
      feedbackRating: "down",
      feedbackRevision: 4,
      feedbackStatus: "pending",
    });

    expect(mergeChatHistory([message("down", 4, "inactive")], [stale])[0]).toMatchObject({
      feedbackRating: "down",
      feedbackRevision: 4,
      feedbackStatus: "inactive",
    });
  });

  it("accepts a genuinely newer server feedback revision", () => {
    const optimistic = message("down", 4, "pending");
    const newer = message("up", 5, "active");

    expect(mergeChatHistory([optimistic], [newer], new Set(["assistant-1"]))[0]).toMatchObject({
      feedbackRating: "up",
      feedbackRevision: 5,
      feedbackStatus: "active",
    });
  });
});
