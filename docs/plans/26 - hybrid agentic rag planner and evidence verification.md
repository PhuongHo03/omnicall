# Phase 26 - Hybrid Agentic RAG Planner And Evidence Verification

## Status: Done

## Objectives

1. Move Agentic RAG to a hybrid Planner -> Retrieval -> Verify -> Replan -> Synthesis flow.
2. Bound iterations, replans, tool calls, chunks, tokens, and provider execution time.
3. Keep canonical processed JSON and PostgreSQL-derived chunks as the only evidence source.
4. Preserve existing SSE compatibility while exposing planner, verification, and replan progress.
5. Remove the unused `synthesize_answer` tool and keep `AnswerSynthesizer` as the synthesis boundary.

## Runtime Defaults

- `max_iterations=2`
- `max_replans=1`
- `max_tool_calls_per_iteration=4`
- `max_chunks_per_tool=5`
- `max_total_chunks=12`
- `max_context_tokens=4000`
- `iteration_timeout_seconds=30`
- `total_timeout_seconds=60`

## Tasks

### Agent contracts and orchestration

- [x] Add schema-validated query planning for single- and multi-intent questions.
- [x] Add deterministic planner fallback and section aliases.
- [x] Add bounded retrieval orchestration and tool-call parameter validation.
- [x] Add evidence verification with required fields, missing fields, and citation checks.
- [x] Add one bounded replan using prior evidence plus verifier feedback.
- [x] Keep fast path before planning and validate its response contract.
- [x] Keep `AnswerSynthesizer`; remove `synthesize_answer` as an LLM tool.

### Retrieval and safety

- [x] Expose metadata, quality, extraction, evidence, and transcript coverage sections through `search_section`.
- [x] Align section registry across chunk builder, retrieval, tools, and citations.
- [x] Clarify primary/fallback semantics for action, decision, risk, and participant tools.
- [x] Treat retrieved text as data, not instructions in planner/synthesis prompts.
- [x] Normalize Vietnamese/English aliases and accents in deterministic planning.

### Runtime, events, and frontend

- [x] Wire all runtime limits through Settings, `.env.example`, Compose, worker, and direct service construction.
- [x] Enforce planner, retrieval, verifier, synthesis, iteration, and total timeouts.
- [x] Preserve existing SSE events and add `agent_plan`, `agent_verify`, and `agent_replan`.
- [x] Update frontend event types, watcher, pending metadata, and status rendering without exposing chain-of-thought.
- [x] Add planner, verifier, replan, evidence, timeout, and fallback observability metadata/metrics.

### Tests and documentation

- [x] Add canonical JSON-backed planner/verifier fixtures for participant, action, risk, metadata, and multi-intent queries.
- [x] Add backend unit, retrieval, integration, timeout, safety, and SSE-compatible coverage.
- [x] Add frontend build and SSE compatibility coverage.
- [x] Update backend/frontend explanations and the project overview after verification.

### 1. Fast Path Boundary

- [x] Keep fast path before Planner and outside `agentIterations`.
- [x] Validate `{needsRag, answer}` and fall back to Planner for invalid output.
- [x] Preserve `fast_path` SSE and separate metrics.

### 2. Query Planner Contract

- [x] Define `intent`, `subQueries`, `sections`, `requiredFields`, `retrievalMode`, and `confidence`.
- [x] Support single- and multi-intent queries with Vietnamese/English normalization.
- [x] Keep deterministic fallback and never expose raw prompts/reasoning.

### 3. Section Registry

- [x] Add a shared section registry for chunk builder and Agent tools.
- [x] Cover metadata, quality, extraction, evidence, and transcript coverage sections.
- [x] Test registered builder priorities and JSON pointers.

### 4. Retrieval Orchestration

- [x] Map plans to bounded parallel retrieval calls.
- [x] Clamp limits, reject invalid values, deduplicate calls, and preserve prior evidence.

### 5. Structured Tool Semantics

- [x] Mark primary and fallback sections in action, decision, risk, and participant tool metadata.
- [x] Keep final answer synthesis outside the retrieval tool catalog.

### 6. Evidence Verifier

- [x] Verify required fields, matched sections, answer presence, and known citations.
- [x] Reject unknown citations and classify no-evidence results as `not_enough_evidence`.

### 7. Replan

- [x] Replan once from prior evidence and verifier `missingFields`.
- [x] Emit sanitized replan metadata and prevent repeated plans.

### 8. Final Synthesis

- [x] Use `AnswerSynthesizer` with accumulated context only.
- [x] Remove `synthesize_answer` from catalog, registry, executor, tests, and runtime docs.

### 9. Settings And Limits

- [x] Wire all Agent limits through Settings, env example, Compose, worker, and service defaults.

### 10. Timeout And Cancellation

- [x] Enforce Think, tool, synthesis, iteration, and total timeout boundaries.
- [x] Preserve partial evidence on timeout and avoid unbounded sequential retries.

### 11. Prompt And Retrieval Safety

- [x] Mark retrieved content as untrusted data in Agent and synthesis prompts.
- [x] Keep prompts, provider responses, and chain-of-thought out of client metadata.

### 12. SSE Contract

- [x] Preserve legacy events and add `agent_plan`, `agent_verify`, and `agent_replan`.

### 13. Frontend

- [x] Update SSE types, watcher, status messages, persisted metadata, and compatibility behavior.
- [x] Keep typewriter, citations, pending recovery, and no raw reasoning display.

### 14. Observability

- [x] Persist intent, sections, iterations, replans, tools, missing fields, evidence, and verification metadata.
- [x] Add Prometheus metrics for iterations, replans, tools, fast path, and latency.

### 15. Test Fixtures And Quality Evaluation

- [x] Add planner/verifier fixtures for participant, action, risk, metadata, aliases, and multi-intent queries.
- [x] Add citation, prompt-boundary, timeout, and section-registry regression tests.

### 16. Integration And E2E Tests

- [x] Cover fast path, simple flow, multi-intent/replan, no evidence, partial failure, fallback, guardrail, and SSE event order.
- [x] Verify persisted metadata mapping and frontend build.

### 17. Documentation

- [x] Update Phase 26, project overview, backend explanation, and frontend explanation.
- [x] Keep infrastructure changes documented through runtime/backend configuration sections.

## Verification Plan

### Automated Tests

- [x] Backend agent/retrieval/integration test discovery (`237 tests OK`).
- [x] Planner schema, fallback, supported sections, tool limits, verifier, and replan tests.
- [x] Timeout handling and prompt-boundary coverage.
- [x] SSE-compatible event and persisted metadata coverage.
- [x] Frontend TypeScript/Vite build.

### Manual Verification

- [x] Fast path greeting and meeting clarification covered by agent tests.
- [x] Simple one-iteration question covered by agent integration tests.
- [x] Multi-intent planner/verifier/replan fixture.
- [x] Unsupported question behavior covered by evidence fallback tests.
- [x] Tool/provider timeout and SSE recovery paths covered by backend/frontend tests.
- [x] Citation and JSON pointer behavior covered by retrieval tests.

### Acceptance Criteria

- [x] Simple questions normally complete in one iteration.
- [x] Complex questions use at most one replan by default.
- [x] Final answers are generated only from verified canonical JSON-derived evidence.
- [x] Invalid tools/parameters cannot bypass server limits.
- [x] All generated JSON sections have a supported retrieval path.
- [x] Existing and new SSE consumers remain compatible.

## Completion Report

> **Completed at:** 2026-07-13
> **Verified by:** backend test suite, frontend build, and persisted chat results from meeting `8fdbf90c-ece8-430a-b456-13bad587e2b5`

### What was implemented

- Hybrid Planner -> Retrieval -> Verify -> bounded Replan -> Synthesis flow.
- Settings-controlled iteration, replan, tool, chunk, token, and timeout limits.
- Canonical JSON-derived retrieval with evidence metadata and verification states.
- `not_enough_evidence` handling, timeout fallback, and removal of the unused `synthesize_answer` tool.
- Backward-compatible SSE plus planner, verification, and replan events.
- Persisted planner, evidence, iteration, replan, and tool metadata.

### Scope decisions

- Phase 26 is complete for the core Agentic RAG architecture and runtime contract.
- Guardrail false positives, answer-quality tuning, and richer multi-message UI presentation are deferred to follow-up work; they do not block the core Phase 26 acceptance criteria.

### Post-completion correctness fixes

- [x] Route price/cost, participant, and business/entity questions to the matching canonical JSON sections.
- [x] Correct irregular `knowledge.records` entity pluralization so `entity.profile` chunks are indexed.
- [x] Make keyword and structured-section retrieval token-aware for normalized Vietnamese/English queries.
- [x] Avoid requiring absent participant roles and provide a qualified entity fallback when the LLM is overly conservative.
- [x] Rebuild meeting `8a7eab47-c4dc-4d03-92e3-85cd59dfd904` retrieval index and verify representative answers.

## Implementation Note

The Phase 26 implementation is complete for the repository code paths covered by automated verification. Manual production-data and browser SSE verification remain operational follow-ups.

### Verified foundation

- Schema-shaped deterministic planning, evidence verification, and bounded replanning.
- Runtime limits, section retrieval additions, fast-path validation, prompt data boundaries, and Agent metrics.
- Backward-compatible SSE planner/verification/replan events and frontend status handling.
- Removal of `synthesize_answer` from the LLM tool surface.
- Backend targeted suite: `54 tests OK`.
- Backend full discovery: `244 tests OK`.
- Frontend TypeScript/Vite build, Compose validation, Python compile, and `git diff --check` passed.

### Operational follow-ups

- [x] Run manual verification against a real processed meeting and confirm persisted evidence/citations/JSON pointers.
- [ ] Run browser-level SSE reconnect verification in the deployed local stack (follow-up UI verification).
- [ ] Add production latency/quality baseline measurements after representative traffic is available.

## Related Docs

- [x] `docs/plans/0 - project overview.md`
- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md` not required; Compose env wiring is documented in backend/runtime explanations
