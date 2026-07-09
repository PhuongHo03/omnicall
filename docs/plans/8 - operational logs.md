# Phase 8 - Operational Logs

## Status: Done

## Objectives

1. Add an Admin-only realtime log page for end-to-end processing and RAG activity.
2. Keep operational events temporary and bounded in Redis instead of PostgreSQL.
3. Show enough session, file, provider, model, timing, count, and safe error context to diagnose failures.

## Prerequisites

- [x] Processing, RAG, Redis, backend Admin auth, and frontend Admin Portal are available.

## Tasks

### Redis Operational Event Stream

- [x] Add a structured operational event provider backed by a Redis Stream.
- [x] Limit retained events with `MAXLEN` and expire the stream with a TTL.
- [x] Restrict event levels to `info` and `error`.
- [x] Redact credentials, tokens, prompts, and raw transcript fields.
- [x] Make event writes fail-open so Redis logging cannot break processing or chat.
- [x] Add tail filtering by flow, level, and search text.
- [x] Add clear behavior without adding a database table or migration.

### Processing Instrumentation

- [x] Emit file-upload and queue events.
- [x] Emit worker receive/lock and processing lifecycle events.
- [x] Emit transcription, audio preprocessing, VAD, ASR, and diarization events.
- [x] Resolve the transcription route before the start event so provider/model context points at text extraction or ASR instead of a router placeholder.
- [x] Emit transcript guardrail and LLM analysis events. *(Transcript guardrail emission removed later in Phase 13)*
- [x] Record primary LLM failure and effective Ollama fallback provider/model when fallback occurs.
- [x] Emit processed JSON validation/persistence, embedding, Milvus upsert, result, and safe failure events.

### RAG Instrumentation

- [x] Emit question and chat-session context.
- [x] Emit input/context/output guardrail events.
- [x] Mark non-strict guardrail provider outages as `info`/`warned` events because chat continues and persists normally.
- [x] Emit query embedding, retrieval source, retrieved chunk IDs/counts, and rerank events.
- [x] Emit primary LLM failure, effective fallback, answer metadata, and persistence events.

### Admin API And Frontend

- [x] Add Admin-only `GET /api/admin/logs`.
- [x] Add Admin-only `DELETE /api/admin/logs`.
- [x] Add `/admin/logs` and the Admin Portal `Logs` link.
- [x] Add Processing Logs and RAG Chat Logs tabs.
- [x] Add `All`, `Info`, and `Error` filters, search, tail size, manual refresh, and two-second live polling.
- [x] Polish the logs toolbar search icon, Tail selector, and Live toggle controls.
- [x] Render complete summary information in each event row without requiring event selection.
- [x] Add a selected-event detail panel for full structured metadata.
- [x] Add a confirmation dialog before clearing logs.

## Verification Plan

### Automated Tests

- [x] Backend operational-log service tests.
- [x] Processing pipeline event instrumentation tests.
- [x] RAG event instrumentation tests.
- [x] Full backend unittest suite.
- [x] Frontend TypeScript/Vite production build.
- [x] Docker Compose config validation.

### Manual Verification

- [x] `/admin/logs` returns the frontend through NGINX.
- [x] Admin can read operational logs through the gateway.
- [x] User receives `403 admin_access_required`.
- [x] Redis stream has the configured TTL and contains structured events.
- [x] Admin clear endpoint removes the current stream.
- [x] Backend, worker, frontend, NGINX, and Redis are healthy after recreation.

### Acceptance Criteria

- [x] No operational-log database table or migration exists.
- [x] Processing and RAG events include session/file/provider/model context when available.
- [x] UI updates automatically and can tail up to 1,000 retained events.
- [x] Logging failures do not fail product workflows.
- [x] Admin authorization remains enforced by the backend.

---

## Completion Report

> **Completed at:** 2026-06-19
> **Verified by:** 88 backend tests, frontend production build, Compose validation, Redis inspection, and gateway smoke checks.

### What was implemented

- Added a capped Redis Stream with a 24-hour sliding TTL and a default tail of 100 events.
- Added detailed processing and RAG structured events with safe error and provider fallback visibility.
- Adjusted non-strict guardrail provider timeouts/outages to appear as warning-status info events instead of red failure events.
- Corrected transcription log provider/model naming by reporting the resolved text or voice route.
- Added Admin-only tail and clear APIs.
- Added `/admin/logs` with realtime polling, filtering, event rows, metadata detail, clear confirmation, and polished toolbar controls.

### What was changed from original plan

- Realtime updates use authenticated two-second polling rather than browser `EventSource`, avoiding bearer tokens in query strings.
- Operational logs are intentionally temporary and independent from durable security audit events.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/plans/0 - project overview.md`
