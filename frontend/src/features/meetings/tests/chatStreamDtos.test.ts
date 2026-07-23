import { describe, expect, it } from "vitest";

import { parseChatStreamEvent } from "../dtos/chatStreamDtos";

describe("chat stream DTOs", () => {
  it("rejects legacy agent events", () => {
    const event = parseChatStreamEvent({
      type: "agent_search",
      iteration: 2,
      tools: [
        "search_semantic",
        "private_admin_tool",
        { tool: "search_records", arguments: { query: "private-query" } },
      ],
      toolArguments: { secret: true },
    });

    expect(event).toBeNull();
  });

  it("sanitizes the persisted assistant payload before dispatch", () => {
    const event = parseChatStreamEvent({
      type: "done",
      turnId: "turn-1",
      answer: "Alice là khách hàng.",
      assistantMessage: {
        id: "assistant-1",
        role: "assistant",
        content: "Alice là khách hàng.",
        retrieved_chunk_ids: ["chunk-1"],
        citations: [],
        feedback_rating: "up",
        feedback_revision: 3,
        metadata: {
          evidenceState: "grounded",
          agentThoughts: ["private reasoning"],
          agentMemoryUsed: ["private-memory"],
        },
        created_at: "2026-07-15T00:00:00Z",
      },
    });

    expect(event).toMatchObject({
      type: "done",
      assistantMessage: {
        id: "assistant-1",
        feedbackRating: "up",
        feedbackRevision: 3,
        metadata: { evidenceState: "grounded" },
      },
    });
    expect(JSON.stringify(event)).not.toContain("private");
  });

  it("rejects unknown or malformed events", () => {
    expect(parseChatStreamEvent({ type: "agent_search", iteration: "one", tools: [] })).toBeNull();
    expect(parseChatStreamEvent({ type: "private_event", payload: "secret" })).toBeNull();
    expect(parseChatStreamEvent("not-an-event")).toBeNull();
  });
});
