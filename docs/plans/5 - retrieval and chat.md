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
- [x] Accept both object-shaped and string-shaped processed JSON items when building retrieval chunks.
- [x] Preserve segment references from provider outputs such as `cites: ["seg-..."]` when deriving chunk citation metadata.
- [x] Create transcript-entry fallback chunks from the same processed JSON and label them as fallback evidence.
- [x] Store chunk metadata in PostgreSQL: meeting, source type, source IDs, time range, token count, and visibility.
- [x] Keep chunk text derived and rebuildable from the processed JSON.
- [x] Filter low-signal filler from retrieval chunks while preserving transcript entries in the JSON.
- [x] Generate embeddings for chunks.
- [x] Upsert derived vectors into Milvus.
- [x] Store stable PostgreSQL chunk references: `meetingId`, `resultId`, `chunkId`, `jsonPointer`, `sourceType`, `sectionType`, `startTime`, and `endTime`.
- [x] Store stable Milvus vector references: `meetingId`, `resultId`, `chunkId`, `jsonPointer`, `sourceType`, `sectionType`, `startTime`, and `endTime`.
- [x] Load authoritative chunk records from PostgreSQL after vector search.
- [x] Load authoritative chunk records from PostgreSQL after PostgreSQL fallback retrieval.
- [x] Enforce account-owner and meeting permission before and after retrieval.
- [x] Rank structured JSON section chunks above plain transcript chunks when both are relevant.
- [x] Pin relevant structured sections for common Vietnamese/English overview, reason/cause, return/refund/process, action, risk, decision, and timeline questions before rerank.
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
- [x] Implement `GET /api/meetings/{meetingId}/chat` so the UI can recover the meeting-scoped thread without managing a separate chat-session ID.
- [x] Implement authorized uploaded asset content reads for browser playback.
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
- [x] Disable upload/record/process controls when the selected meeting status cannot accept that operation.
- [x] Show an authenticated audio playback panel above the processed JSON when a ready meeting has an uploaded audio asset.

## Verification Plan

### Automated Tests

- [x] Add authorization tests for chat access.
- [x] Add retrieval service tests using deterministic fixtures.
- [x] Add tests that structured JSON chunks outrank plain transcript chunks for summary/action/risk/timeline questions.
- [x] Add regression tests for string-shaped LLM sections and Vietnamese overview, reason/cause, and return/refund/process intent pinning.
- [x] Add tests for "not enough evidence" behavior.
- [x] Add tests for LLM provider fallback behavior when primary provider fails.
- [x] Add tests that retrieved vector IDs are revalidated against PostgreSQL permissions.
- [x] Add chat persistence tests for user message, assistant answer, and citations.
- [x] Add meeting-scoped chat history reload and empty-history tests.
- [x] Build frontend chat tab with TypeScript/Vite.
- [x] Add regression test for local embedding vector hits without text evidence.

### Manual Verification

- [x] Ask questions over one processed meeting.
- [x] Rebuild `test7` retrieval chunks and confirm Vietnamese overview/action/risk questions retrieve structured chunks before transcript fallback.
- [x] Recheck `test8` (`23b31ae6-f5a5-46e0-bb4c-63e0a901093e`) and confirm Vietnamese reason/return-process questions retrieve detailed summary, requirements, constraints, blockers, follow-ups, and key points instead of unrelated entity/transcript snippets.
- [x] Ask `test7` "Những ý chính trong cuộc gọi này" through the gateway chat API and confirm a grounded answer with summary/key-point citations.
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
> **Verified by:** `python3 -m compileall backend`; `docker compose config`; backend `unittest` suite; Milvus upsert/search smoke checks; frontend `npm run build`; frontend image build; gateway frontend health check; manual gateway chat smoke over processed text transcript; meeting-scoped chat redesign reverified on 2026-06-19. The 9-table schema consolidation was reverified on 2026-06-19 with 62 backend unittest tests, frontend production build, healthy backend/worker containers, gateway health smoke, and PostgreSQL table-count checks.

### What was implemented

- Phase 5 is complete. The retrieval slice is implemented:
  - `meeting_chunks` PostgreSQL table and repository.
  - Model-backed local text embedding provider for retrieval indexing.
  - Retrieval chunk builder from processed JSON sections, with structured sections prioritized above transcript fallback chunks.
  - Flexible processed JSON indexing for string-shaped sections and provider outputs that cite transcript segment IDs directly.
  - Worker integration that rebuilds retrieval chunks after each successful processed result.
  - Job retrieval metadata recording chunk count and embedding provider/model.
- The first chat backend slice is implemented:
  - meeting-scoped `chat_messages` table.
  - Milvus REST vector search with PostgreSQL authoritative record reload.
  - Intent-pinned structured retrieval for broad Vietnamese/English overview, reason/cause, return/refund/process, action, risk, decision, and timeline questions before local rerank.
  - PostgreSQL fallback retrieval ranking over authoritative `meeting_chunks`.
  - PostgreSQL authoritative scope checks for Milvus hits before chunks are used as evidence.
  - `POST /api/meetings/{meetingId}/chat` and `GET /api/meetings/{meetingId}/chat`, with one public chat thread per meeting.
  - Cited assistant responses with retrieved chunk IDs, processed-section pointers, transcript ranges, and evidence state.
  - LLMProvider answer generation with local retrieval-summary fallback on provider failure.
  - Chat metadata records the effective LLM provider/model that actually generated the answer, so endpoint/API-first operation is visible even when an Ollama fallback wrapper is configured.
- The frontend chat slice is implemented:
  - Chatbot-style meeting workspace with the meeting history/create controls in a left sidebar.
  - `MeetingActionPanel` for one-file intake, recording, process/retry, and progress display.
  - `MeetingAssetPlaybackPanel` above processed JSON for uploaded audio playback through an authenticated backend asset-content endpoint.
  - `MeetingIntelligenceResultPanel` for readable processed JSON sections after a meeting is ready.
  - `MeetingChatPanel` below the processed result for question input, chat history, evidence state, and citations.
  - Chat API and DTO mapping for ask/history responses.
  - Hook orchestration that stores only lightweight chat UI state and reloads the meeting thread from the backend whenever a ready meeting is reopened.
  - Safe backend error display through the existing event strip.

### What was changed from original plan

- MVP retrieval indexing persists authoritative chunk records and local embeddings in PostgreSQL first, then upserts derived vectors to Milvus.
- Chunk metadata stores `tokenCount` instead of a token range for the first slice.
- Chat uses Milvus vector search when available and falls back to PostgreSQL ranking when the vector index is unavailable or empty.
- LLM selection preserves the configured priority: API/private endpoint primary first, then Ollama fallback only when the primary provider fails.
- Frontend chat is displayed under the processed JSON result in the main workspace; source-opening/navigation remains a later UX improvement after richer transcript/insight reader screens exist.
- Frontend and backend now follow one meeting asset per analysis lineage: retry processing reuses the uploaded asset, and a different file requires creating a new meeting.
- Phase 5 established the RAG storage/search/chat flow. Phase 5.5 replaces the temporary embedding path with local Ollama text embeddings and adds rerank.
- Added a backend asset-content endpoint and frontend Blob URL playback path so ready audio meetings can replay the original uploaded file above the processed JSON without exposing MinIO directly.
- Fixed the `test7` chat regression where broad Vietnamese questions retrieved only noisy transcript snippets. The indexer now keeps string-shaped summary/analysis items, and retrieval pins relevant structured sections before rerank; `test7` was re-indexed and verified with a grounded gateway chat response.
- Fixed the `test8` chat regression where Vietnamese reason/return-process questions such as "Tại sao khách lại muốn đổi trả áo?" and "Khách có thể đổi trả hàng như nào?" retrieved weak entity/transcript snippets. Retrieval now pins detailed summary, requirements, constraints, blockers, follow-ups, and key points for these intents, and the chat prompt asks the LLM to synthesize structured meeting intelligence as a meeting analyst instead of answering from one isolated chunk.
- Simplified the public chat contract to one meeting-scoped thread. The frontend and API no longer expose or accept `chatSessionId`; the database schema now stores chat directly in `chat_messages.meeting_id`.

### Notes for future sessions

- Milvus uses the REST adapter to avoid adding a Python gRPC build dependency to the local image.
- Tests use test-only embedding fixtures; production retrieval now expects configured model embeddings.
- Phase 6 can start from admin/operations endpoints and dashboard work.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/plans/0 - project overview.md`
