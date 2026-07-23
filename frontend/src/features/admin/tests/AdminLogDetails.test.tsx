import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AdminLogDetails } from "../components/AdminLogDetails";
import type { AdminOperationalLog } from "../types/adminTypes";


describe("AdminLogDetails", () => {
  it("shows hydrated chat content while keeping duplicated bodies out of event metadata", () => {
    const event: AdminOperationalLog = {
      id: "1-0",
      timestamp: "2026-07-21T00:00:00Z",
      level: "info",
      flow: "rag",
      stage: "answer",
      status: "succeeded",
      message: "Deterministic fast-path answer persisted.",
      workspaceId: "user-1",
      meetingId: "meeting-1",
      meetingName: "Meeting",
      file: {},
      chat: {
        turnId: "turn-1",
        userMessageId: "user-message-1",
        assistantMessageId: "assistant-message-1",
        questionPreview: "Full question",
        question: "Full question",
        answer: "Full answer"
      },
      provider: "local-direct-intent",
      model: null,
      executorType: "local",
      resource: "closed-direct-intent-router",
      operation: "persist_direct_answer",
      version: null,
      configuredProvider: null,
      configuredModel: null,
      effectiveProvider: "local-direct-intent",
      effectiveModel: null,
      originProvider: null,
      originModel: null,
      fallbackUsed: false,
      durationMs: null,
      details: {},
      errorType: null,
      errorMessage: null
    };

    const { container } = render(<AdminLogDetails event={event} />);

    expect(screen.getByText("Full question")).toBeInTheDocument();
    expect(screen.getByText("Full answer")).toBeInTheDocument();
    expect(screen.getByText("local-direct-intent")).toBeInTheDocument();
    expect(screen.getByText("closed-direct-intent-router")).toBeInTheDocument();
    const raw = container.querySelector(".admin-log-json pre")?.textContent ?? "";
    expect(raw).not.toContain('"question": "Full question"');
    expect(raw).not.toContain('"answer": "Full answer"');
    expect(raw).toContain('"turnId": "turn-1"');
  });
});
