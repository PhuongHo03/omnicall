import { describe, expect, it } from "vitest";

import { parseMeetingChatHistory } from "../dtos/meetingDtos";
import { appendLivePipelineStage } from "../states/chatState";

describe("pipelineTrace v1", () => {
  it("parses Simple RAG stages and ignores legacy agent traces", () => {
    const history = parseMeetingChatHistory({
      meeting_id: "meeting-1",
      title: "Meeting",
      messages: [{
        id: "message-1", role: "assistant", content: "Answer",
        retrieved_chunk_ids: [], citations: [], feedback_rating: null,
        feedback_revision: null, created_at: "2026-07-22T00:00:00Z",
        metadata: {
          evidenceState: "direct", answerOriginKind: "llm_synthesis",
          agentFlow: { version: 1 }, agentRawFlow: { version: 1 },
          pipelineTrace: {
            version: 1, contract: "simple-rag.v1",
            stages: [{ stage: "synthesis", status: "succeeded", durationMs: 12, provider: "endpoint", model: "qwen", details: { attempts: 1 } }],
          },
        },
      }],
    });
    expect(history.messages[0].metadata.pipelineTrace?.stages[0].stage).toBe("synthesis");
    expect("agentFlow" in history.messages[0].metadata).toBe(false);
    expect("agentRawFlow" in history.messages[0].metadata).toBe(false);
  });

  it("builds an in-progress trace from live SSE stages and ignores queued", () => {
    const requestGate = appendLivePipelineStage(undefined, "request_gate");
    const retrieval = appendLivePipelineStage(requestGate, "retrieval");
    const ignored = appendLivePipelineStage(retrieval, "queued");

    expect(retrieval?.stages).toMatchObject([
      { stage: "request_gate", status: "succeeded" },
      { stage: "retrieval", status: "in_progress" },
    ]);
    expect(ignored).toEqual(retrieval);
  });
});
