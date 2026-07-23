import { describe, expect, it } from "vitest";

import { adminLogProvenanceRows } from "../components/adminLogProvenance";
import type { AdminOperationalLog } from "../types/adminTypes";

function event(overrides: Partial<AdminOperationalLog>): AdminOperationalLog {
  return {
    id: "1-0",
    timestamp: "2026-07-21T00:00:00Z",
    level: "info",
    flow: "processing",
    stage: "vector_upsert",
    status: "succeeded",
    message: "done",
    workspaceId: null,
    meetingId: null,
    meetingName: null,
    file: {},
    chat: {},
    provider: null,
    model: null,
    executorType: null,
    resource: null,
    operation: null,
    version: null,
    configuredProvider: null,
    configuredModel: null,
    effectiveProvider: null,
    effectiveModel: null,
    originProvider: null,
    originModel: null,
    fallbackUsed: null,
    durationMs: null,
    details: {},
    errorType: null,
    errorMessage: null,
    ...overrides
  };
}

describe("adminLogProvenanceRows", () => {
  it("labels a Milvus collection as a collection instead of a model", () => {
    const rows = adminLogProvenanceRows(event({
      executorType: "vector_store",
      effectiveProvider: "milvus-rest",
      resource: "meeting_chunks"
    }));
    expect(rows).toContainEqual(["Vector Store", "milvus-rest"]);
    expect(rows).toContainEqual(["Collection", "meeting_chunks"]);
    expect(rows.some(([label]) => label === "Model")).toBe(false);
  });

  it("shows the answer producer first when a cached answer is served", () => {
    const rows = adminLogProvenanceRows(event({
      executorType: "cache",
      effectiveProvider: "redis",
      resource: "exact-answer-cache",
      originProvider: "ollama",
      originModel: "qwen2.5:1.5b",
      details: { served: true }
    }));
    expect(rows).toContainEqual(["Answer Provider", "ollama"]);
    expect(rows).toContainEqual(["Answer Model", "qwen2.5:1.5b"]);
    expect(rows).toContainEqual(["Cache Store", "redis"]);
    expect(rows.some(([label]) => label.startsWith("Configured"))).toBe(false);
  });

  it("does not present configured defaults as runtime provenance", () => {
    const rows = adminLogProvenanceRows(event({
      executorType: "pipeline",
      stage: "agent",
      status: "started",
      configuredProvider: "openai-compatible",
      configuredModel: "google/gemma-4-E4B-it",
      operation: "answer_generation"
    }));
    expect(rows).toEqual([
      ["Executor", "Pipeline"],
      ["Operation", "answer_generation"]
    ]);
  });

  it("shows only the effective LLM on a completed provider step", () => {
    const rows = adminLogProvenanceRows(event({
      executorType: "llm",
      effectiveProvider: "ollama",
      effectiveModel: "qwen2.5:1.5b",
      configuredProvider: "openai-compatible",
      configuredModel: "google/gemma-4-E4B-it",
      fallbackUsed: true
    }));
    expect(rows).toContainEqual(["LLM Provider", "ollama"]);
    expect(rows).toContainEqual(["LLM Model", "qwen2.5:1.5b"]);
    expect(rows.some(([label]) => label.startsWith("Configured"))).toBe(false);
  });

  it("labels deterministic local logic as an implementation without a model", () => {
    const rows = adminLogProvenanceRows(event({
      executorType: "local",
      effectiveProvider: "local-direct-intent",
      resource: "closed-direct-intent-router"
    }));
    expect(rows).toContainEqual(["Implementation", "local-direct-intent"]);
    expect(rows).toContainEqual(["Component", "closed-direct-intent-router"]);
    expect(rows.some(([label]) => label === "Provider" || label === "Model")).toBe(false);
  });
});
