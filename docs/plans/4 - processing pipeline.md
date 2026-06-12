# Phase 4 - Processing Pipeline

## Status: Done

## Objectives

1. Process uploaded meeting assets asynchronously.
2. Persist a complete processed transcript JSON containing transcript and structured meeting intelligence.
3. Make worker execution idempotent and retry-safe.
4. Produce a complete processed transcript JSON suitable as the chatbot's primary knowledge base.

## Prerequisites

- [x] Phase 3 meeting upload is complete.
- [x] Worker service can consume RabbitMQ tasks.
- [x] ASR and analysis provider choices are configured.

## Tasks

### Worker

- [x] Add worker entrypoint and task registration.
- [x] Add thin task/listener boundary that delegates to use cases.
- [x] Use Redis locks for meeting processing.
- [x] Check current job state before mutations.
- [x] Load latest meeting, asset, and job state from PostgreSQL before processing.
- [x] Mark job `RUNNING`, `SUCCEEDED`, or `FAILED` through a service layer.
- [x] Add explicit `RETRYING` transition behavior when retry policy is implemented.
- [x] Store provider request IDs or job metadata when available for audit/debug.
- [x] Ensure worker can resume or safely skip already-completed stages.

### Providers

- [x] Add transcription provider interface.
- [x] Add analysis provider interface.
- [x] Implement `LLMProvider` with provider selection order: API provider, private endpoint, then Ollama local fallback.
- [x] Support OpenAI-compatible private endpoints and non-OpenAI custom endpoints behind the same application boundary.
- [x] Add Ollama adapter for local small-model fallback.
- [x] Add optional document text extraction interface for uploaded meeting notes or transcripts.
- [x] Keep provider credentials in backend/worker env only.
- [x] Normalize deterministic provider stub outputs into the persisted JSON contract.
- [x] Normalize LLM-generated provider outputs into the persisted JSON contract before persistence.
- [x] Define full provider timeout, retry, and failure classification behavior.
- [x] Validate processed JSON output after every LLM provider response, including Ollama fallback.
- [x] Record which provider/model generated each `meeting_intelligence_result`.

### Persistence

- [x] Persist a versioned `meeting_intelligence_result` JSON for each successful processing run.
- [x] Include transcript segments inside the processed JSON.
- [x] Include structured result sections: summaries, analysis, outcomes, decisions, action items, important notes, timeline items, risks, blockers, dependencies, topics, entities, follow-ups, open questions, and quality warnings.
- [x] Persist optional normalized/indexed rows for transcript segments and insight items only when needed for query, filtering, or citations.
- [x] Persist source ranges/citation IDs for structured items when transcript evidence exists.
- [x] Persist the full processed JSON in PostgreSQL JSONB for the MVP slice.
- [x] Mark meeting `READY` or `FAILED`.
- [x] Record structured failure reason without leaking credentials, prompts, or stack traces.

### Processed Transcript JSON

- [x] Segment transcript by time and speaker label in the deterministic provider stub.
- [x] Segment uploaded text transcript files by timestamp and speaker label when available.
- [x] Generate an executive summary for quick recall.
- [x] Generate a detailed summary grouped by topic, agenda section, or discussion flow.
- [x] Extract key points grouped by topic.
- [x] Extract decisions with confidence, decision owner when available, and source references.
- [x] Extract action items with owner, task, due date, priority, status, and source references when present.
- [x] Extract important notes that are neither tasks nor decisions but should be remembered.
- [x] Extract timeline items: dates, deadlines, milestones, follow-up checkpoints, launch/release targets, and commitments.
- [x] Extract placeholder risks, dependencies, impact, and mitigation notes in the deterministic provider stub.
- [x] Extract real risks, blockers, dependencies, uncertainty, impact, and mitigation notes when available.
- [x] Extract follow-ups and unresolved questions with suggested owner or team when available.
- [x] Include outcomes, requirements, constraints, assumptions, conflicts, metrics, parking-lot topics, and glossary sections in the schema.
- [x] Extract entities such as people, teams, products, customers, projects, and systems.
- [x] Extract short important quotes only when they help traceability.
- [x] Link extracted stub items to transcript citation IDs.
- [x] Normalize dates and owners when possible while preserving original wording.
- [x] Filter low-value filler content from structured analysis and retrieval chunks without deleting transcript entries from the JSON.
- [x] Validate required top-level processed JSON sections before marking the meeting `READY`.
- [x] Store extraction warnings when a section is incomplete due to missing real ASR/analysis providers.

### Result Quality Gates

- [x] Require at least one summary section and transcript coverage metadata before `READY`.
- [x] Mark optional sections as empty-with-reason instead of silently omitting them.
- [x] Track processing result version so future reprocessing can use a newer schema.
- [x] Keep transcript entries and derived sections distinguishable inside the same JSON so users can inspect evidence.
- [x] Make processed JSON rebuildable from source asset, provider configuration, and schema version.

### API Read Models

- [x] Implement `GET /api/meetings/{meetingId}/transcript`.
- [x] Implement `GET /api/meetings/{meetingId}/insights`.
- [x] Implement `GET /api/meetings/{meetingId}/intelligence-result` if the UI or export flow needs the complete JSON.
- [x] Let transcript/insight APIs read from the processed JSON or from indexed views derived from it.
- [x] Shape `GET /api/meetings/{meetingId}/insights` around the processed transcript JSON sections.
- [x] Shape responses for frontend review screens without exposing provider prompts.

## Verification Plan

### Automated Tests

- [x] Add worker idempotency tests.
- [x] Add failure/retry tests.
- [x] Add provider selection tests for API, private endpoint, and Ollama fallback.
- [x] Add transcript normalization tests using deterministic fixtures.
- [x] Add insight schema validation tests.
- [x] Add processed result completeness tests for summary, action item, timeline, risk, and note sections.
- [x] Add source-link tests that validate extracted items reference existing transcript segments.
- [x] Add processed JSON schema validation tests for required top-level sections.
- [x] Add tests that failed provider calls update job and meeting state safely.
- [x] Add live API test coverage for worker-backed intelligence result, transcript, and insights endpoints.

### Manual Verification

- [x] Process one uploaded meeting file.
- [x] Confirm transcript and insight sections are visible through backend APIs.
- [x] Confirm user-facing insight output includes summary, detailed analysis, notes, decisions, action items, timeline, risks, blockers, dependencies, follow-ups, and open questions.
- [x] Confirm transcript entries remain available inside the processed JSON even when summaries omit filler.
- [x] Confirm at least one extracted item links back to the correct transcript evidence.

### Acceptance Criteria

- [x] Retried jobs do not duplicate durable records or side effects.
- [x] Malformed or failed processing records a clear failure state.
- [x] A processed meeting has transcript segments, structured insights, and a `READY` status inside the processed JSON or indexed views derived from it.
- [x] A processed meeting has a versioned processed transcript JSON that can drive chatbot retrieval.
- [x] Required processed result sections are present or explicitly marked empty with a reason.
- [x] Worker business logic lives in services/use cases, not broker listener glue.
- [x] Provider-specific data does not leak into public API contracts.

---

## Completion Report

> **Completed at:** 2026-06-12
> **Verified by:** `python3 -m compileall backend`, `docker compose --env-file .env.example config`, `alembic current`, backend `unittest` suite, gateway health check, and healthy backend/worker/nginx containers

### What was implemented

- Phase 4 is complete.
- Implemented the first worker-backed processing slice: Celery worker, RabbitMQ queue consumption, Redis processing lock, deterministic ASR/analysis provider stubs, JSONB persistence for `meeting_intelligence_result`, and read APIs for transcript, insights, and complete intelligence JSON.
- Verified one uploaded `.wav` meeting through the gateway. The meeting reached `READY`, the processing job reached `SUCCEEDED`, and the persisted JSON used schema `meeting-intelligence-result.v1`.
- Updated the backend unittest flow to assert worker-backed result persistence and the three intelligence read endpoints.
- Added `LLMProvider` adapters for OpenAI-compatible API/private endpoints, custom JSON endpoints, Ollama, and primary-to-Ollama fallback selection.
- Added `LLMAnalysisProvider`, gated by `ANALYSIS_PROVIDER=llm`, to generate `meeting-intelligence-result.v1` sections from LLM JSON while preserving the authoritative ASR transcript and falling back to deterministic analysis on provider failure.
- Added worker service tests for locked jobs, already-succeeded job skip behavior, duplicate-result prevention, and provider failure state transitions.
- Added `DocumentTextExtractionProvider` for `.txt`, `.md`, `.vtt`, and `.srt` transcript or note uploads. Text uploads are parsed into transcript segments and recorded with `source.transcriptionProvider=local-text-extraction`.
- Added derived PostgreSQL rows for `transcript_segments` and `meeting_insights`, rebuilt from the versioned JSON result for retrieval/filter/citation workflows.
- Added rule-based deterministic extraction for decisions, action items, notes, timeline items, risks, blockers, dependencies, follow-ups, questions, metrics, entities, and important quotes.
- Added LLM retry/backoff configuration and retryable provider failure classification.

### What was changed from original plan

- The MVP slice stores the complete processed JSON in PostgreSQL JSONB. Optional normalized transcript/insight rows remain planned until retrieval and filtering need them.
- Production audio ASR, speaker diarization, production prompt evaluation, embedding, rerank, chunking, and Milvus upsert are moved out of Phase 4 completion scope. They belong to provider hardening and Phase 5 retrieval/chat work.

### Notes for future sessions

- The current transcription and analysis providers are deterministic placeholders. They validate the processing contract, not production insight quality.
- The LLM analysis path is implemented and tested behind `ANALYSIS_PROVIDER=llm`, but local Compose defaults to deterministic analysis until a real provider endpoint is configured.
- RabbitMQ 4 rejects Celery remote-control pidbox transient queues in this local setup, so the worker disables remote control/gossip/mingle and uses a socket healthcheck.
- `meeting_intelligence_result` remains the source of truth. `transcript_segments` and `meeting_insights` are derived rows and can be rebuilt from source asset, provider config, and schema version.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
- [x] `docs/plans/5 - retrieval and chat.md`
