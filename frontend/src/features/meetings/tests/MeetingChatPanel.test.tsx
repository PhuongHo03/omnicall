import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MeetingChatPanel } from "../components/MeetingChatPanel";
import type { MeetingChatMessage } from "../types/meetingTypes";

function assistantMessage(pending: boolean): MeetingChatMessage {
  return {
    id: pending ? "local:pending" : "message-1",
    role: "assistant",
    content: pending ? "Đang xử lý..." : "Đã hoàn tất",
    retrievedChunkIds: [],
    citations: [],
    metadata: pending
      ? { local: true, pending: true }
      : { evidenceState: "grounded", feedbackEligible: true },
    feedbackRating: null,
    feedbackRevision: 0,
    createdAt: "2026-07-15T00:00:00Z",
  };
}

describe("MeetingChatPanel busy state", () => {
  it("keeps the controlled question while a prior turn is busy and enables it afterwards", () => {
    const commonProps = {
      disabled: false,
      onCitationClick: vi.fn(),
      onFeedback: vi.fn(),
      onQuestionChange: vi.fn(),
      onSubmitQuestion: vi.fn(),
      onTypewriterComplete: vi.fn(),
      pendingFeedbackMessageIds: new Set<string>(),
      question: "Ai là khách hàng?",
      typewriterMessageIds: new Set<string>(),
    };
    const { rerender } = render(
      <MeetingChatPanel {...commonProps} messages={[assistantMessage(true)]} />,
    );

    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("textbox")).toHaveValue("Ai là khách hàng?");

    rerender(<MeetingChatPanel {...commonProps} messages={[assistantMessage(false)]} />);
    expect(screen.getByRole("textbox")).toBeEnabled();
    expect(screen.getByRole("textbox")).toHaveValue("Ai là khách hàng?");
  });
});
