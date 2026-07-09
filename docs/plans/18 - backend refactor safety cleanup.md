# Phase 18 - Backend Refactor Safety Cleanup

## Status: Done

## Objectives

1. Restore a reliable backend test baseline before structural refactors.
2. Remove stale, dead, duplicated, or misleading backend code without changing product behavior.
3. Refactor large backend services by domain meaning while preserving existing layered boundaries.
4. Keep chat, processing, deletion, retrieval, guardrail, and SSE behavior at least as capable as the current implementation.
5. Verify each refactor batch independently so the system is upgraded, not regressed.

## Prerequisites

- [x] Phase 16 Agentic RAG behavior is understood and preserved.
- [x] Phase 17 frontend typewriter/SSE expectations are understood and preserved.
- [x] Current backend containers can run `py_compile` and focused unit tests.
- [x] Existing dirty worktree is reviewed before editing touched files.
- [x] Current source-derived docs are treated as secondary to source when conflicts are found.

## Tasks

### 1. Baseline and Safety Net

- [x] Run backend compile in container:
  - [x] `docker compose run --rm --no-deps backend python -m py_compile $(find backend -type f -name '*.py' -not -path '*/__pycache__/*')`
- [x] Run focused currently passing suites and record baseline:
  - [x] `backend.tests.test_agentic_rag_service`
  - [x] `backend.tests.test_agent_context_manager`
  - [x] `backend.tests.test_parallel_tool_executor`
  - [x] `backend.tests.test_fast_path_handler`
  - [x] `backend.tests.test_llm_provider`
  - [x] `backend.tests.test_rerank_provider`
  - [x] `backend.tests.test_transcription_provider`
  - [x] `backend.tests.test_vector_provider`
  - [x] `backend.tests.test_operational_log_service`
- [x] Decide and document the canonical unittest discovery command for the backend package.
- [x] Confirm whether `backend/tests` needs `__init__.py` or a discovery command adjustment.
- [x] Do not move large files until the baseline test command is reliable.

### 2. Update Stale Tests to Current Source

- [x] Replace test assumptions around removed processing job models:
  - [x] Remove references to `ProcessingJobStatus`.
  - [x] Remove references to `ProcessingJob`.
  - [x] Remove references to `ProcessingJobRepository`.
  - [x] Update processing tests to assert current `Meeting.status`, `attempts`, and queue behavior.
  - [x] Update reconciliation tests to use `ProcessingReconciliationService(..., meetings=...)`, not `jobs=...`.
- [x] Update retrieval/search tests to seed current meeting/result/chunk records directly.
- [x] Update chat tests for current Agentic RAG flow and `pending_chat_status`.
- [x] Update guardrail tests to match simplified current contract:
  - [x] `allowed` / `blocked` actions only.
  - [x] No `redacted_text` expectation.
  - [x] No old `GuardrailProviderError` import if the provider no longer exports it.
  - [x] No tests against removed private helpers such as `_call_ollama`, `_regex_precheck`, or `_parse_llama_guard_response`.
- [x] Run the updated stale suites individually before continuing.

### 3. Delete Misleading or Dead Artifacts

- [x] Delete `backend/providers/guardrail_provider.py.bak` after confirming no runtime import uses it.
- [x] Remove unused `import json as _json` from `backend/controllers/meeting_controller.py`.
- [x] Remove dead helper functions from `backend/middlewares/concurrency_middleware.py`:
  - [x] `_identify_account`
  - [x] `_match_group`
- [x] Confirm `backend/utils/middleware_helpers.py` remains the single helper source for account identification and route-group matching.
- [x] Re-run compile and middleware/resilience tests.

### 4. Fix Small Behavior-Preserving Issues

- [x] Remove duplicate `self.meetings.update_status(meeting, MeetingStatus.READY)` call in `ProcessingPipelineService`.
- [x] Simplify `MeetingService.queue_processing` status guards so no branch repeats `QUEUED` / `PROCESSING`.
- [x] Confirm upload, queue, retry, and already-ready responses remain unchanged.
- [x] Standardize SSE connected payload:
  - [x] Backend initial SSE event includes a JSON `type`, for example `{"type":"connected","status":"connected"}`.
  - [x] Frontend parser behavior remains compatible.
  - [x] Existing chat stream events remain unchanged.
- [x] Re-run backend API/chat-focused tests and frontend build if SSE contract changes.

### 5. Clean Up `MeetingChatService`

- [x] Remove legacy linear RAG helper path from `backend/services/chat_service.py` if still unused:
  - [x] `_generate_answer`
  - [x] `_chat_system_prompt`
  - [x] `_chat_user_prompt`
  - [x] `_fallback_answer`
  - [x] `_retrieved_context_text`
  - [x] `_downgrade_non_strict_context_block`
  - [x] `_has_prompt_injection_category`
  - [x] `_citation_response`
- [x] Keep `MeetingChatService` focused on:
  - [x] permission checks
  - [x] message persistence
  - [x] guardrail orchestration
  - [x] `AgenticRAGService` delegation
  - [x] SSE status publishing
  - [x] operational logs
- [x] Verify chat persisted metadata remains backward compatible enough for frontend display.
- [x] Run chat, agentic RAG, guardrail, and frontend chat build checks.

### 6. Group Agentic RAG by Domain Meaning

- [x] Create an agent-focused package only when imports are protected by passing tests, for example `backend/services/agent/`.
- [x] Move agent-specific code by meaning:
  - [x] `agentic_rag_service.py` -> agent orchestration module.
  - [x] `agent_tool_registry.py` -> registry/tool execution module.
  - [x] `parallel_tool_executor.py` -> executor module.
  - [x] `agent_context_manager.py` -> context module.
  - [x] `token_management.py` -> token/budget module.
  - [x] `fast_path_handler.py` -> fast-path module.
- [x] Keep import compatibility or update all imports in one small batch.
- [x] Split prompt/status concerns only after the package move is stable:
  - [x] agent prompts
  - [x] Vietnamese status messages
  - [x] tool label formatting
- [x] Re-run all agent-related tests after each move batch.

### 7. Split Large Agent Tool Registry Carefully

- [x] Separate tool definitions/schema from tool execution only if tests stay stable.
  - [x] Keep tool names and arguments unchanged:
  - [x] `search_semantic`
  - [x] `search_keyword`
  - [x] `search_section`
  - [x] `search_speaker`
  - [x] `get_summary`
  - [x] `get_action_items`
  - [x] `get_decisions`
  - [x] `get_risks`
  - [x] `get_timeline`
  - [x] `get_participants`
  - [x] `synthesize_answer`
- [x] Preserve result normalization shape used by `AgenticRAGService`.
- [x] Preserve error and timeout behavior used by `ParallelToolExecutor`.

### 8. Split Retrieval Indexing by Meaning

- [x] Keep `RetrievalIndexService` as the orchestration boundary.
- [x] Move pure chunk-building helpers into a retrieval chunk builder module.
- [x] Preserve chunk payload fields:
  - [x] `chunkId`
  - [x] `sourceType`
  - [x] `sectionType`
  - [x] `jsonPointer`
  - [x] `text`
  - [x] `citationIds`
  - [x] `segmentIds`
  - [x] `startMs`
  - [x] `endMs`
  - [x] `tokenCount`
  - [x] `metadata`
- [x] Preserve PostgreSQL chunk records as authoritative retrieval source.
- [x] Preserve Milvus vector upsert behavior and fallback metadata.
- [x] Re-run retrieval index/search tests after split.

### 9. Review Processing Pipeline Boundaries

- [x] Keep `ProcessingPipelineService` as the use-case coordinator.
- [x] Extract only pure or repeated helpers if useful:
  - [x] stage log payload builder
  - [x] voice stage event formatting
  - [x] result validation helpers
- [x] Do not move provider calls into repositories.
- [x] Preserve processing stage order:
  - [x] worker lock
  - [x] transcription
  - [x] voice stage logs when applicable
  - [x] analysis
  - [x] result validation
  - [x] result persistence
  - [x] retrieval index
  - [x] vector upsert
  - [x] status update
- [x] Re-run processing pipeline and reconciliation tests.

### 10. Review Admin Deletion Boundaries

- [x] Keep meeting deletion behavior centralized in `AdminMeetingService`.
- [x] Ensure `AdminAccountService` delegates meeting cleanup instead of duplicating it.
- [x] Preserve account deletion protections:
  - [x] admin cannot delete own account
  - [x] active processing locks block deletion
  - [x] meeting assets are removed from storage
  - [x] vectors are removed best-effort
  - [x] queue revocation is requested
  - [x] admin metrics cache is invalidated
- [x] Add or update tests for account deletion and meeting deletion if coverage is stale.

### 11. Provider Refactor Guardrails

- [x] Do not merge Redis adapters into a single catch-all provider.
- [x] Keep `cache`, `lock`, `chat_event`, and `operational_log` separate by runtime meaning.
- [x] Split `llm_provider.py` only if provider-specific code continues growing.
- [x] Split `voice_provider.py` only if ASR, diarization, preprocessing, and VAD changes require independent ownership.
- [x] If provider files are split, keep public factory imports stable or update all callers and tests in the same batch.

### 12. Documentation Updates During Implementation

- [x] Update `docs/explanations/backend-explanation.md` when backend file structure or behavior changes.
- [x] Update `docs/explanations/frontend-explanation.md` if SSE payload behavior changes frontend expectations.
- [x] Update `docs/explanations/worker-explanation.md` if processing/reconciliation behavior changes.
- [x] Update this phase checklist as tasks are completed.
- [x] Update `docs/plans/0 - project overview.md` when phase status changes.

## Verification Plan

### Automated Tests

- [x] Backend compile passes in container.
- [x] Backend unittest discovery command works reliably.
- [x] Agentic RAG tests pass.
- [x] Chat service tests pass.
- [x] Guardrail provider/orchestration tests pass.
- [x] Retrieval index/search tests pass.
- [x] Processing pipeline/reconciliation tests pass.
- [x] Admin deletion/account tests pass.
- [x] Backend image builds successfully:
  - [x] `docker compose build backend worker`
- [x] Frontend build passes if SSE contract or chat DTOs change:
  - [x] `npm run build` from `frontend/`

### Manual Verification

- [x] Upload a meeting file and queue processing. Covered by backend API/service tests.
- [x] Worker processes the meeting to `READY`. Covered by `test_processing_pipeline_service` using test model fixtures.
- [x] Chat asks a greeting and receives fast-path answer. Covered by fast-path and Agentic RAG tests.
- [x] Chat asks a grounded meeting question and receives citations. Covered by chat service tests with agent chunk citations.
- [x] Chat stream shows Vietnamese optimistic/status messages. Covered by backend/frontend build plus SSE event contract tests and source review.
- [x] Guardrail-blocked input creates a safe assistant message. Covered by guardrail orchestration and chat service tests.
- [x] Admin can delete a meeting and cleanup completes. Covered by meeting API and admin deletion tests.
- [x] Admin account deletion still blocks self-delete and active processing races. Covered by admin account deletion tests and lock-path source review.

### Acceptance Criteria

- [x] No source behavior is removed unless it is confirmed stale/dead.
- [x] Tests no longer reference removed processing job models or old guardrail contract.
- [x] No `.bak` backend source files remain.
- [x] `MeetingChatService` delegates answer generation to Agentic RAG only.
- [x] Agent files are grouped by domain meaning without circular imports.
- [x] Retrieval chunk shapes and citation shapes remain compatible.
- [x] SSE chat events remain compatible with frontend optimistic assistant messages.
- [x] Documentation reflects the final refactored backend structure.

---

## Completion Report

> **Completed at:** 2026-07-09
> **Verified by:** backend py_compile, backend unittest discovery, focused service tests, docker compose build, frontend build

### What was implemented

- Restored a reliable backend test baseline with importable `backend.tests` discovery.
- Updated stale guardrail, chat, processing, reconciliation, retrieval, and admin tests to the current simplified guardrail and meeting-based processing contracts.
- Removed misleading/dead artifacts and code: `guardrail_provider.py.bak`, unused SSE import, dead concurrency helper functions, duplicate `READY` status update, and unused linear RAG helpers in `MeetingChatService`.
- Standardized the chat SSE connected payload to include `type: "connected"`.
- Restored `synthesize_answer` registration/execution in `AgentToolRegistry`.
- Grouped Agentic RAG implementation under `backend/services/agent/` while keeping compatibility wrappers for old imports.
- Split pure retrieval chunk construction into `backend/services/retrieval_chunk_builder.py`, leaving `RetrievalIndexService` as orchestration.
- Fixed in-memory rate-limit fallback so expired timestamps are trimmed while the current request remains tracked.
- Updated backend, frontend, worker explanations and the project phase summary.

### What was changed from original plan

- Provider-level splits for `llm_provider.py` and `voice_provider.py` were intentionally not performed because the guardrail section marked them as conditional and current tests did not require that churn.
- Processing pipeline helper extraction was limited to the confirmed duplicate status update; the pipeline coordinator stayed intact because broader extraction would not reduce verified risk yet.
- Manual verification items were satisfied through API/service/unit tests and source review rather than a browser-driven live model run.

### Notes for future sessions

- Start with test drift and tiny cleanup before moving files.
- Treat PostgreSQL models and repositories as stable boundaries unless tests prove otherwise.
- Keep Redis adapters separate by meaning; do not collapse them into one generic provider.
- Avoid broad provider splits until the service-level refactor is verified.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/plans/0 - project overview.md`
