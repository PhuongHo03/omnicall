# Phase 9 - Full JSON RAG Coverage

## Status: Done

## Objectives

1. Make meeting chat use as much of the processed JSON as possible as the meeting knowledge base.
2. Add retrieval coverage for top-level JSON sections that are currently displayed but not indexed.
3. Preserve structured metadata such as participants, speakers, roles, quality warnings, source/model context, timestamps, confidence, owners, statuses, and due dates in chunk text and metadata.
4. Improve intent pinning so factual questions about people, counts, source quality, metadata, and missing evidence retrieve the right JSON sections before rerank.
5. Keep the local development data path simple: reset or rebuild old retrieval data instead of preserving stale chunk formats.

## Prerequisites

- [x] Phase 5 retrieval and chat are implemented.
- [x] Phase 5.5 rerank is implemented.
- [x] Phase 5.6 guardrails are implemented.
- [x] Phase 8 operational logs are implemented for retrieval and RAG debugging.
- [x] Confirm whether the phase should reset all local meeting data or only rebuild `meeting_chunks` and Milvus vectors from stored `meeting_intelligence_results`.

## Current Coverage Snapshot

### Currently Indexed

- [x] `summary.executive`
- [x] `summary.detailed`
- [x] `summary.keyPoints`
- [x] `analysis.*` list sections except `analysis.emptySections`
- [x] `transcript.segments[].text` as fallback evidence

### Former Gaps Closed

- [x] `meeting`: title, started time, duration.
- [x] `source`: asset IDs, object keys, generated time, transcription provider/model, analysis provider/model, LLM provider/model, voice metadata, transcript guardrail metadata.
- [x] `participants`: names, speaker labels, roles, details, confidence, referenced segments, participant count.
- [x] `transcript.coverage`: coverage status and covered asset IDs.
- [x] `transcript.segments[]` metadata: speaker, start/end time, confidence, and text together.
- [x] `analysis.emptySections`: explicit "no evidence" explanations.
- [x] `citations`: citation IDs, referenced segment IDs, and time ranges as a compact navigational/evidence map.
- [x] `quality`: coverage, warnings, confidence, ASR/diarization/guardrail warnings.
- [x] Item metadata inside indexed sections: owner, assignee, due date, status, priority, role, type, category, confidence, details, references, and other scalar/list values that are not the first text-like field.
- [x] Planned product sections from the project overview that are not first-class runtime schema fields yet: agenda, customer/user feedback, decisions pending approval, and sentiment/tone remain documented future schema work rather than invented runtime fields.

## Tasks

### JSON Coverage Inventory

- [x] Add source-derived retrieval index tests that compare runtime processed JSON sections against generated chunk IDs.
- [x] Add fixture JSON covering every runtime top-level section: `meeting`, `source`, `participants`, `transcript`, `summary`, `analysis`, `citations`, and `quality`.
- [x] Add fixture JSON covering runtime `analysis` subsection behavior, including `emptySections`.
- [x] Add fixture JSON with rich nested item metadata such as owner, status, due date, role, confidence, details, and referenced segment IDs.
- [x] Decide whether planned-but-not-runtime sections should become schema fields now or remain documented future work.

### Chunk Builder

- [x] Add `meeting.metadata` chunks for title, duration, and started time.
- [x] Add `source.processing` chunks for provider/model/generated-at metadata.
- [x] Add `source.voiceMetadata` chunks for audio duration, preprocessing, VAD, ASR, diarization, warning, and model context.
- [x] Add `source.guardrails` chunks for transcript guardrail action, categories, warnings, and strict/non-strict behavior.
- [x] Add `participants.overview` chunk with participant count and participant names/roles.
- [x] Add `participants.participant` chunks for each participant, including name/speaker, role, details, confidence, and references.
- [x] Add `transcript.coverage` chunk for coverage status and covered asset IDs.
- [x] Enrich transcript fallback chunks so speaker, time range, and confidence are available to retrieval and citations, not only raw text.
- [x] Add `analysis.emptySections` chunks so chat can answer which sections lacked evidence and why.
- [x] Add `quality.overview` and `quality.warning` chunks for confidence, coverage, and warnings.
- [x] Add a compact `citations.map` chunk for citation count, referenced segment count, and evidence time range without polluting normal semantic retrieval with every citation row.
- [x] Keep each chunk stable with deterministic `chunkId`, `sectionType`, `jsonPointer`, `sourceId`, citation IDs, segment IDs, start/end times, token count, visibility, and metadata.

### Rich Text Serialization

- [x] Replace single-field `_item_text` extraction with a safe structured serializer for retrieval text.
- [x] Include meaningful scalar fields such as title, name, role, owner, assignee, status, due date, priority, category, confidence, and details.
- [x] Include short list values such as tags, segment IDs, citation IDs, participants, dependencies, and related entities when useful.
- [x] Keep noisy/internal fields out of embedding text when they do not help answer users, such as raw object keys unless the section is specifically source metadata.
- [x] Keep raw transcript and prompt-like sensitive content out of operational logs; retrieval chunks may contain transcript text because they are product evidence.
- [x] Add tests proving action item owner/status/due date, participant role/details, quality warnings, and transcript speaker/confidence appear in chunk text or metadata.

### Retrieval And Intent Pinning

- [x] Add people/participant intents for Vietnamese and English questions: who joined, how many people, attendee list, speaker roles.
- [x] Add meeting metadata intents: meeting title, duration, start time.
- [x] Add quality intents: confidence, warnings, low-quality audio, transcript coverage, ASR/diarization issues.
- [x] Add source/model intents: which model/provider processed the meeting, when analysis was generated, which asset was used.
- [x] Add missing-evidence intents: which sections are empty, what the system could not determine.
- [x] Add entity/glossary/metric intents so those analysis sections are pinned when directly asked.
- [x] Keep existing overview, reason/cause, process, action, risk, decision, and timeline pinning behavior.
- [x] Ensure intent-pinned chunks merge with vector/rerank candidates without starving high-relevance semantic hits.

### Answer Generation

- [x] Update chat prompt/context formatting to expose section labels clearly, including metadata sections.
- [x] Teach answer generation to answer count/list questions directly from structured chunks when possible.
- [x] Preserve `not_enough_evidence` only when the expanded JSON context still does not support the answer.
- [x] Return citations for metadata chunks in a way the frontend can display without requiring transcript timestamps.
- [x] Keep transcript citations available when participant/detail chunks reference transcript segments.

### Data Reset And Reindexing

- [x] For local development, add a documented reset path that can delete stale `meeting_chunks`, Milvus vectors, chat messages, and optionally processed meetings.
- [x] Prefer a rebuild command or script that reindexes all existing `meeting_intelligence_results` into the new chunk format when preserving meetings is useful.
- [x] If simpler during local development, document `docker compose down -v` plus migration and model-init steps as the clean-start path.
- [x] Ensure reset/rebuild behavior does not become a production data-loss path.
- [x] Add a clear note that old chat answers may cite stale chunk IDs until chat history is cleared or meetings are reprocessed.

### API And Frontend

- [x] Confirm existing chat response DTOs can represent metadata chunks without transcript time ranges.
- [x] Improve citation display labels for `participants`, `meeting`, `source`, `quality`, and `analysis.emptySections`.
- [x] Keep frontend state lightweight; do not duplicate backend retrieval logic in the browser.
- [x] Add a documented backend command for rebuilding retrieval indexes when needed.

### Documentation

- [x] Update `docs/explanations/backend-explanation.md` after implementation to document full JSON chunk coverage.
- [x] Update `docs/explanations/frontend-explanation.md` if citation UI behavior changes.
- [x] Update `docs/explanations/worker-explanation.md` if processing/reindex behavior changes.
- [x] Update `docs/explanations/infrastructure-explanation.md` if reset/rebuild commands affect Compose or Milvus/Redis usage.
- [x] Update `docs/plans/0 - project overview.md` when the phase starts or completes.

## Verification Plan

### Automated Tests

- [x] Retrieval chunk builder tests cover every runtime top-level JSON section.
- [x] Retrieval chunk builder tests cover runtime `analysis` behavior, including `emptySections`.
- [x] Retrieval chunk builder tests prove participant count/name/role/detail chunks are generated.
- [x] Retrieval chunk builder tests prove quality warnings and source/model metadata chunks are generated.
- [x] Retrieval search tests prove Vietnamese/English participant-count questions pin participant chunks.
- [x] Retrieval search tests prove quality/source/meeting-metadata questions pin the right sections.
- [x] Chat service tests prove participant-count questions return grounded answers when chunks exist.
- [x] Regression tests preserve existing action, risk, decision, timeline, overview, reason, and process retrieval behavior.
- [x] Reindex/reset smoke checks verify the rebuild command is available.
- [x] Run the backend unittest suite.
- [x] Run the frontend TypeScript/Vite production build if citation UI changes.

### Manual Verification

- [x] Deterministic chat-service verification covers: "Cuộc gọi này có bao nhiêu người tham gia?"
- [x] Retrieval-search verification covers participant list/role section pinning.
- [x] Retrieval-search verification covers source/model section pinning.
- [x] Retrieval-search verification covers: "Chất lượng transcript có cảnh báo gì không?"
- [x] Retrieval-search verification covers meeting metadata section pinning.
- [x] Retrieval-search verification covers missing-evidence section pinning.
- [x] Confirm answers cite `participants`, `meeting`, `source`, `quality`, or `analysis.emptySections` chunks when those are the best evidence.
- [x] Confirm normal summary/action/risk/timeline questions still prefer structured meeting intelligence over raw transcript snippets.

### Acceptance Criteria

- [x] The RAG knowledge base covers all runtime processed JSON top-level sections.
- [x] Metadata-rich fields are searchable and answerable, not only rendered in the processed JSON panel.
- [x] Participant count/list/role questions no longer return `not_enough_evidence` when `participants` exists.
- [x] Quality/source/model/meeting-metadata questions are grounded in structured chunks.
- [x] Existing transcript-backed citations still work.
- [x] Keep structured participant-count facts citation-backed: reducer assigns citations for speaker-derived counts and reindexing resolves legacy `sourceWindowIds`/speaker-derived facts.
- [x] Keep planner and participant retrieval tool contracts aligned so count-only questions do not require participant names.
- [x] Route attendee/joined/participated aliases through the participant planner branch.
- [x] Preserve requested section priority before applying the bounded per-tool context limit.
- [x] Give JSON-only metadata chunks stable citation IDs so the output evidence gate can preserve grounded metadata answers.
- [x] Local development has a clean reset or rebuild path for stale chunks and vectors.
- [x] Documentation accurately describes the new RAG coverage and any local reset/reindex workflow.

---

## Completion Report

> **Completed at:** 2026-06-25
> **Verified by:** backend targeted tests, full backend unittest suite, frontend production build, Compose validation, rebuild-script smoke check, and local container/gateway health checks.

### What was implemented

- Added full processed-JSON retrieval chunk coverage for meeting metadata, source/provider/model/voice/guardrail metadata, participants, summaries, analysis, empty sections, transcript coverage, quality warnings, citation overview, and enriched transcript segments.
- Replaced first-text-field item extraction with structured metadata serialization so owners, roles, statuses, dates, confidence, details, and references are searchable.
- Added participant, quality, source/model, meeting metadata, missing-evidence, metric, entity, and glossary intent pinning while preserving existing summary/action/risk/decision/timeline behavior.
- Updated chat prompt context and frontend citation labels so metadata chunks are valid, understandable sources.
- Added `backend.scripts.rebuild_retrieval_index` for local reindexing and optional chat-history clearing after chunk format changes.

### What was changed from original plan

- Planned product sections that are not runtime schema fields yet were left as future schema work instead of being invented by the indexer.
- Live LLM manual prompts were verified through deterministic retrieval/search/chat service tests to avoid making Phase 9 depend on local provider latency or generated wording.

### Notes for future sessions

- Existing processed meetings need `python -m backend.scripts.rebuild_retrieval_index --clear-chat` inside the backend environment, or a full local `docker compose down -v` reset and reprocess, before old local data has the new chunk shape.
- The local stack was rebuilt and recreated for backend, worker, frontend, and gateway after implementation.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
- [x] `docs/PROJECT_PLAN.md`
