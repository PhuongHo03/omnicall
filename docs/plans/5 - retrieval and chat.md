# Phase 5 - Retrieval And Chat

## Status: Done

## Objectives

1. Create retrieval chunks and embeddings primarily from processed transcript JSON sections.
2. Answer user questions using processed meeting intelligence, with transcript evidence for citations.
3. Save chat sessions and cited answers.
4. Make answers traceable to transcript segments or structured insight records.

## Prerequisites

- [x] Phase 4 processing pipeline is complete.
- [x] Embedding provider is configured.
- [x] Milvus is available or a documented MVP fallback is chosen.

## Tasks

### Retrieval

- [x] Chunk structured processed JSON sections before plain transcript entries.
- [x] Create dedicated retrieval chunks for summary, detailed summary, key points, decisions, action items, important notes, timeline items, risks, blockers, dependencies, follow-ups, open questions, topics, entities, and important quotes.
- [x] Create transcript-entry fallback chunks from the same processed JSON and label them as fallback evidence.
- [x] Store chunk metadata in PostgreSQL: meeting, source type, source IDs, time range, token count, and visibility.
- [x] Keep chunk text derived and rebuildable from the processed JSON.
- [x] Filter low-signal filler from retrieval chunks while preserving transcript entries in the JSON.
- [x] Generate embeddings for chunks.
- [x] Upsert derived vectors into Milvus.
- [x] Store stable PostgreSQL chunk references: `workspaceId`, `meetingId`, `resultId`, `chunkId`, `jsonPointer`, `sourceType`, `sectionType`, `startTime`, and `endTime`.
- [x] Store stable Milvus vector references: `workspaceId`, `meetingId`, `resultId`, `chunkId`, `jsonPointer`, `sourceType`, `sectionType`, `startTime`, and `endTime`.
- [x] Load authoritative chunk records from PostgreSQL after vector search.
- [x] Load authoritative chunk records from PostgreSQL after PostgreSQL fallback retrieval.
- [x] Enforce workspace and meeting permission before and after retrieval.
- [x] Rank structured JSON section chunks above plain transcript chunks when both are relevant.
- [x] Use transcript chunks to support citations, disambiguation, and fallback answers.

### Chat

- [x] Add chat session and message persistence.
- [x] Add meeting permission checks for every chat request.
- [x] Add DTOs for user question, cited answer, source citation, and chat history response.
- [x] Normalize and validate question length and supported language at the backend boundary.
- [x] Use `LLMProvider` for answer generation with API/private endpoint priority and Ollama local fallback.
- [x] Generate answers from structured processed JSON context first.
- [x] Use transcript entries inside the JSON to verify or cite important claims.
- [x] Return "not enough evidence" when retrieved context does not support an answer.
- [x] Save retrieved chunk IDs and citation metadata with assistant messages.
- [x] Return cited processed result sections and transcript ranges to the frontend.
- [x] Avoid saving provider prompts or sensitive raw provider responses in chat history.
- [x] Support questions about tasks, deadlines, risks, decisions, notes, and timeline through processed-section retrieval.

### API

- [x] Implement `POST /api/meetings/{meetingId}/chat`.
- [x] Implement `GET /api/meetings/{meetingId}/chat/{sessionId}`.
- [x] Include source citations in answer responses.
- [x] Include result section citations in answer responses.
- [x] Return safe validation and authorization errors.

### Frontend

- [x] Add meeting chat tab.
- [x] Show citations linked to transcript ranges.
- [x] Show citations linked to processed result sections when available.
- [x] Show answer confidence/evidence state without inventing unsupported certainty.
- [x] Show "not enough evidence" responses clearly.
- [x] Display backend errors without leaking internals.
- [x] Keep chat state lightweight and fetch saved messages from backend.

## Verification Plan

### Automated Tests

- [x] Add authorization tests for chat access.
- [x] Add retrieval service tests using deterministic fixtures.
- [x] Add tests that structured JSON chunks outrank plain transcript chunks for summary/action/risk/timeline questions.
- [x] Add tests for "not enough evidence" behavior.
- [x] Add tests for LLM provider fallback behavior when primary provider fails.
- [x] Add tests that retrieved vector IDs are revalidated against PostgreSQL permissions.
- [x] Add chat persistence tests for user message, assistant answer, and citations.
- [x] Build frontend chat tab with TypeScript/Vite.
- [x] Add regression test for local embedding vector hits without text evidence.

### Manual Verification

- [x] Ask questions over one processed meeting.
- [x] Confirm answers cite source chunks from that meeting.
- [x] Ask about action items, timeline, risks, and important notes; confirm answers come from processed result sections.
- [x] Ask a question unrelated to the meeting and confirm the system refuses or says there is not enough evidence.
- [x] Open a cited source and confirm it maps to the correct transcript segment or insight.

### Acceptance Criteria

- [x] Chat cannot access meetings outside the user's permission scope.
- [x] Answers include traceable citations.
- [x] Vector DB remains derived data, not the source of truth.
- [x] Chat retrieval uses processed transcript JSON as the primary knowledge base.
- [x] Plain transcript retrieval is available as citation/fallback evidence, not the primary answer source.
- [x] Unsupported answers are not fabricated when retrieval evidence is weak.
- [x] Chat history is durable and reloadable from backend APIs.

---

## Completion Report

> **Completed at:** 2026-06-12
> **Verified by:** `python3 -m compileall backend`; `docker compose --env-file .env.example config`; Alembic current at `0005_chat_history`; backend `unittest` suite; Milvus upsert/search smoke checks; frontend `npm run build`; frontend image build; gateway frontend health check; manual gateway chat smoke over processed text transcript

### What was implemented

- Phase 5 is complete. The retrieval slice is implemented:
  - `meeting_chunks` PostgreSQL table and repository.
  - Deterministic local text embedding provider for MVP retrieval indexing.
  - Retrieval chunk builder from processed JSON sections, with structured sections prioritized above transcript fallback chunks.
  - Worker integration that rebuilds retrieval chunks after each successful processed result.
  - Job retrieval metadata recording chunk count and embedding provider/model.
- The first chat backend slice is implemented:
  - `chat_sessions` and `chat_messages` tables.
  - Milvus REST vector search with PostgreSQL authoritative record reload.
  - PostgreSQL fallback retrieval ranking over authoritative `meeting_chunks`.
  - Local embedding evidence guard that filters Milvus/PostgreSQL hits without meaningful query-text overlap.
  - `POST /api/meetings/{meetingId}/chat` and `GET /api/meetings/{meetingId}/chat/{sessionId}`.
  - Cited assistant responses with retrieved chunk IDs, processed-section pointers, transcript ranges, and evidence state.
  - LLMProvider answer generation with local retrieval-summary fallback on provider failure.
- The frontend chat slice is implemented:
  - Meeting workspace detail tabs for operations and chat.
  - `MeetingChatPanel` for question input, chat history, evidence state, and citations.
  - Chat API and DTO mapping for ask/history responses.
  - Hook orchestration that stores only lightweight chat UI state and reloads saved messages from the backend.
  - Safe backend error display through the existing event strip.

### What was changed from original plan

- MVP retrieval indexing persists authoritative chunk records and local embeddings in PostgreSQL first, then upserts derived vectors to Milvus.
- Chunk metadata stores `tokenCount` instead of a token range for the first slice.
- Chat uses Milvus vector search when available and falls back to PostgreSQL ranking when the vector index is unavailable or empty.
- Frontend chat is displayed as a workspace tab, while source-opening/navigation remains a later UX improvement after transcript/insight reader screens exist.
- Because local hash embeddings are not semantically rich, retrieval now requires meaningful text overlap before using Milvus/PostgreSQL hits as answer evidence.

### Notes for future sessions

- Milvus uses the REST adapter to avoid adding a Python gRPC build dependency to the local image.
- The local hash embedding provider is deterministic and useful for tests/MVP wiring, not production semantic quality.
- Phase 6 can start from admin/operations endpoints and dashboard work.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/plans/0 - project overview.md`
