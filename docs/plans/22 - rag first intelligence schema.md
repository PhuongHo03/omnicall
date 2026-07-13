# Phase 22 - RAG First Intelligence Schema

## Status: Done

## Objectives

1. Replace the current processed JSON contract with a new `meeting-intelligence-result.v1` that is optimized for precise RAG, factual extraction, and evidence traceability.
2. Keep `meeting_intelligence_results.result_json` as the authoritative knowledge document while treating PostgreSQL `meeting_chunks` and Milvus vectors as rebuildable derived indexes.
3. Extract high-precision participants, speaker counts, facts, events, entities, relationships, actions, decisions, risks, questions, topic summaries, and transcript-backed citations.
4. Reduce dependency on LLM judgment by separating deterministic transcript/source fields, LLM candidate extraction, normalization, verification, and derived facts.
5. Rebuild retrieval so specific factual questions prefer fact/entity/event/relationship records before broader summaries or transcript windows.

## Prerequisites

- [x] Confirm Phase 22 is allowed to break the existing `meeting-intelligence-result.v1` runtime contract.
- [x] Confirm old local `meeting_intelligence_results`, `meeting_chunks`, Milvus vectors, and chat citations do not need compatibility support.
- [x] Confirm the project will reset or reprocess existing local meetings after the new schema lands.
- [x] Confirm the existing PostgreSQL JSONB storage model can remain unchanged.
- [x] Confirm `meeting_chunks` remains rebuildable from `result_json` and Milvus remains a non-authoritative vector index.
- [x] Confirm the preferred LLM provider has enough context capacity for richer extraction prompts.

## Target Knowledge Model

The new `meeting-intelligence-result.v1` should represent the meeting as a RAG-first knowledge document:

```json
{
  "schemaVersion": "meeting-intelligence-result.v1",
  "meeting": {},
  "source": {},
  "transcript": {},
  "evidence": {},
  "speakers": {},
  "participants": [],
  "entities": [],
  "facts": [],
  "events": [],
  "relationships": [],
  "topics": [],
  "summaries": {},
  "actions": [],
  "decisions": [],
  "risks": [],
  "questions": [],
  "quality": {},
  "extraction": {}
}
```

Authoritative layers:

- `transcript` stores original transcript evidence from the voice ASR and diarization pipeline.
- `evidence.citations` stores canonical transcript/time-range evidence records.
- `speakers` stores deterministic diarization and talk-time statistics.
- `participants`, `entities`, `facts`, `events`, `relationships`, `actions`, `decisions`, `risks`, and `questions` store verified structured knowledge.
- `topics` and `summaries` store hierarchical topic and meeting-level summaries.
- `meeting_chunks` and Milvus vectors are derived from the JSON and can be deleted/rebuilt.

## Tasks

### Schema Contract

- [x] Replace the current runtime JSON contract with the new RAG-first `meeting-intelligence-result.v1` shape.
- [x] Define required top-level sections: `meeting`, `source`, `transcript`, `evidence`, `speakers`, `participants`, `entities`, `facts`, `events`, `relationships`, `topics`, `summaries`, `actions`, `decisions`, `risks`, `questions`, `quality`, and `extraction`.
- [x] Define canonical ID prefixes for all records: `seg-`, `cite-`, `speaker-`, `participant-`, `entity-`, `fact-`, `event-`, `rel-`, `topic-`, `action-`, `decision-`, `risk-`, and `question-`.
- [x] Define reference rules for every cross-record field, including participant IDs, entity IDs, event IDs, fact IDs, topic IDs, relationship endpoints, and citation IDs.
- [x] Define stable enum sets for fact types, event types, entity types, relationship types, action statuses, risk statuses, question statuses, evidence types, extraction methods, and confidence levels.
- [x] Decide whether field names use `startMs`/`endMs`, `dueAt`, and `occurredAt` consistently across all records.
- [x] Decide whether records store raw `citationIds` only or also include denormalized `startMs`, `endMs`, and short evidence labels for retrieval text.

### Transcript And Evidence

- [x] Keep `transcript.segments` as the authoritative source text with stable `id`, `speakerLabel`, `startMs`, `endMs`, `text`, and `confidence`.
- [x] Preserve transcript coverage metadata, including covered asset IDs, source kind, extraction route, and known gaps.
- [x] Add `evidence.citations[]` as canonical evidence records with `id`, `segmentIds`, `startMs`, `endMs`, `speakerLabels`, `quote`, and `evidenceType`.
- [x] Generate citation quotes deterministically from transcript segments instead of trusting LLM-generated quotes.
- [x] Support citation records spanning multiple contiguous transcript segments.
- [x] Add citation validation that rejects or repairs unknown segment IDs and invalid time ranges.
- [x] Add evidence warnings for citations that span too much transcript text or point to low-confidence ASR segments.

### Speakers And Participants

- [x] Add deterministic `speakers.speakerCount` from ASR/diarization speaker labels.
- [x] Add `speakers.items[]` with speaker label, segment count, talk time, mapped participant ID, and confidence.
- [x] Add `participants[]` as the canonical participant registry.
- [x] Distinguish `isAttendee` from `isMentionedOnly` so mentioned people are not counted as speakers or attendees.
- [x] Store participant `displayName`, `normalizedName`, `speakerLabels`, `role`, `organization`, `confidence`, and `citationIds`.
- [x] Extract participant identities from direct self-introductions, speaker labels, role statements, and contextual references.
- [x] Add deterministic participant count facts derived from `speakers` and verified participant mappings.
- [x] Add warnings when participant identity resolution is partial, ambiguous, or contradicted by transcript evidence.

### Facts

- [x] Add `facts[]` as atomic, queryable claim records.
- [x] Support factual types for participant counts, identity, roles, dates, deadlines, commitments, requests, amounts, locations, products/services, statuses, and outcomes.
- [x] Store each fact with `id`, `type`, `subject`, `predicate`, `value`, `unit`, `confidence`, `derivedFrom`, and `citationIds`.
- [x] Ensure specific questions such as "how many people joined" can be answered from `facts` and `speakers`, not from summary prose.
- [x] Add a verifier that drops, lowers confidence, or quarantines facts with missing or weak evidence.
- [x] Add `extraction.unsupportedClaims[]` for LLM-proposed claims that cannot be grounded.

### Events And Timeline

- [x] Add `events[]` as normalized timeline records.
- [x] Store each event with `id`, `type`, `title`, `description`, `participantIds`, `entityIds`, `startMs`, `endMs`, `status`, `confidence`, and `citationIds`.
- [x] Extract event types such as customer request, escalation, decision made, action assigned, issue reported, resolution offered, deadline mentioned, and follow-up scheduled.
- [x] Normalize event ordering by transcript time range.
- [x] Link event records to related facts, actions, decisions, risks, and topics.
- [x] Keep transcript-backed citations for every event unless the event is explicitly marked as inferred.

### Entities And Relationships

- [x] Add top-level `entities[]` for organizations, people mentioned, products, services, systems, dates, amounts, locations, documents, and domain terms.
- [x] Store entity aliases and mention citation IDs.
- [x] Move entity extraction out of soft `analysis.entities` and into canonical entity records.
- [x] Add `relationships[]` as graph edges between participants, entities, facts, events, actions, decisions, risks, questions, and topics.
- [x] Support relationship types such as `owns`, `mentions`, `requests`, `blocks`, `depends_on`, `decides`, `causes`, `resolves`, `relates_to`, and `participates_in`.
- [x] Validate relationship endpoints against existing canonical record IDs.
- [x] Add relationship chunks so multi-hop questions can retrieve graph edges directly.

### Actions, Decisions, Risks, And Questions

- [x] Move action items from `analysis.actionItems` into top-level `actions[]`.
- [x] Store actions with task, owner participant/entity reference, status, due date, priority, related event IDs, confidence, and citation IDs.
- [x] Move decisions from `analysis.decisions` into top-level `decisions[]`.
- [x] Store decisions with decision text, maker participant IDs, status, impact, related event IDs, confidence, and citation IDs.
- [x] Move risks and blockers into top-level `risks[]` with type, severity, probability, impact, mitigation, owner, status, and citation IDs.
- [x] Move open questions and follow-up questions into top-level `questions[]` with asker, assignee, status, due date, and citation IDs.
- [x] Preserve backward user-facing concepts such as action items, decisions, risks, blockers, dependencies, and open questions through new canonical records rather than the old `analysis` object.

### Topics And Hierarchical Summaries

- [x] Add `topics[]` as hierarchical topic records with `id`, `title`, `level`, `parentTopicId`, `childTopicIds`, `summary`, `startMs`, `endMs`, `participantIds`, `factIds`, `eventIds`, and `citationIds`.
- [x] Generate first-level topic summaries over contiguous transcript windows.
- [x] Generate higher-level rollup summaries from topic records, not directly from raw transcript only.
- [x] Add `summaries.executive` with citations and topic references.
- [x] Add `summaries.topicLevel[]` and `summaries.timelineLevel[]` for broad-answer retrieval.
- [x] Ensure hierarchical summaries do not invent unsupported facts beyond linked lower-level evidence.
- [x] Add retrieval chunks for topic summaries and summary rollups with lower priority than exact fact/event/entity matches for factual questions.

### Extraction Pipeline

- [x] Split processing into deterministic extraction, LLM candidate extraction, normalization, verification, graph building, hierarchical summarization, and indexing.
- [x] Add deterministic speaker statistics before LLM analysis.
- [x] Update the analysis prompt to request the new RAG-first schema sections.
- [x] Include timestamp, speaker label, and useful confidence/source metadata in the analysis prompt when context budget allows.
- [x] Require the LLM to output candidate participants, facts, events, entities, relationships, actions, decisions, risks, questions, topics, and summaries.
- [x] Normalize names, aliases, statuses, priorities, dates, amounts, and record IDs after LLM extraction.
- [x] Resolve participant/entity/action/decision/risk/question references after normalization.
- [x] Verify all citation IDs and segment IDs before persistence.
- [x] Add confidence scoring that combines transcript confidence, citation quality, LLM extraction confidence, and verifier results.
- [x] Add extraction warnings for partial diarization, unknown names, weak evidence, unsupported claims, and conflicting claims.

### Backend Validation And Persistence

- [x] Update `LLMAnalysisProvider` to build the new canonical JSON shape.
- [x] Update result defaults to create the new top-level sections.
- [x] Update processing validation to enforce required top-level sections.
- [x] Validate transcript segment IDs, citation IDs, participant IDs, entity IDs, fact IDs, event IDs, topic IDs, and relationship endpoints.
- [x] Validate that important record types have citation evidence or an explicit derived/inferred source.
- [x] Validate that deterministic fields are not overwritten by LLM output.
- [x] Keep `meeting_intelligence_results.result_json` as JSONB without adding normalized source-of-truth tables unless a later phase needs them.
- [x] Add a local reset/reprocess path for obsolete v1 JSON data and stale retrieval chunks.

### Retrieval Chunk Builder

- [x] Replace legacy section chunking with RAG-first chunk types.
- [x] Build chunks for `fact.*`, `speaker.stats`, `participant.profile`, `entity.profile`, `event.timeline`, `relationship.edge`, `topic.summary`, `summary.executive`, `summary.topic`, `summary.timeline`, `action.item`, `decision.record`, `risk.record`, `question.record`, and `transcript.window`.
- [x] Preserve deterministic `chunkId`, `sourceType`, `sectionType`, `sourceId`, `jsonPointer`, `citationIds`, `segmentIds`, `startMs`, `endMs`, token count, visibility, and metadata.
- [x] Generate contextual chunk text with meeting title, record type, normalized fields, confidence, and concise evidence labels.
- [x] Generate transcript windows by time/topic/speaker instead of only isolated transcript segment fallback chunks.
- [x] Keep low-signal transcript text out of retrieval chunks while preserving it in `result_json`.
- [x] Ensure facts/events/entities/relationships outrank transcript windows for specific factual questions.
- [x] Ensure topic and executive summaries outrank exact facts only for broad summary questions.

### Retrieval Search And Intent Pinning

- [x] Update intent pinning for participant count, participant identity, attendee list, mentioned people, speaker count, events, timeline, actions, decisions, risks, owners, deadlines, entities, and relationships.
- [x] Route count questions to `fact.participant_count` and `speaker.stats`.
- [x] Route "who joined" questions to `participant.profile` and `speaker.stats`.
- [x] Route "what happened" questions to `event.timeline` and `topic.summary`.
- [x] Route "who owns what" questions to `relationship.edge` and `action.item`.
- [x] Route broad overview questions to `summary.executive`, `summary.topic`, and `topic.summary`.
- [x] Preserve vector retrieval and rerank while allowing intent-pinned exact records to enter the candidate set.
- [x] Add fallback behavior when Milvus is unavailable and only PostgreSQL chunk records are available.

### Chat Context And Answering

- [x] Update chat context formatting to expose record type, canonical ID, confidence, citation IDs, time range, and concise evidence.
- [x] Teach answer generation to answer count/list/date/owner/status questions directly from exact facts or canonical records.
- [x] Require the answer to distinguish speaker count, identified participants, attendees, and mentioned-only people when relevant.
- [x] Require the answer to say when a field is unknown, ambiguous, inferred, or low confidence.
- [x] Preserve cited answers with transcript/time-range evidence.
- [x] Keep `not_enough_evidence` for questions not supported by JSON knowledge records or transcript evidence.

### API And Frontend Impact

- [x] Confirm `GET /api/meetings/{meetingId}/intelligence-result` can return the new JSON without DTO changes.
- [x] Update chat citation labels for facts, speakers, participants, entities, events, relationships, topics, actions, decisions, risks, questions, and transcript windows.
- [x] Confirm the generic result drawer can render the new sections without layout breakage.
- [x] Update any frontend helpers that assume old `summary`, `analysis`, or `citations` paths.
- [x] Preserve frontend ownership boundary: no backend retrieval or extraction logic in the browser.

### Data Reset And Reindexing

- [x] Document the local development reset path for old `meeting_intelligence_results`, `meeting_chunks`, chat messages, and Milvus vectors.
- [x] Update or replace `backend.scripts.rebuild_retrieval_index` so it only rebuilds from the new schema.
- [x] Add a clear failure message when attempting to index obsolete JSON documents.
- [x] Confirm local `docker compose down -v` plus reprocessing is an acceptable clean-start path for Phase 22.
- [x] Confirm stale chat citations are cleared when chunk IDs or section types change.

### Documentation

- [x] Update `docs/explanations/backend-explanation.md` with the new RAG-first intelligence schema, extraction pipeline, validation rules, and chunk types.
- [x] Update `docs/explanations/worker-explanation.md` with deterministic extraction, LLM extraction, verification, graph building, topic summarization, and indexing stages.
- [x] Update `docs/explanations/frontend-explanation.md` if citation labels or result rendering assumptions change.
- [x] Update `docs/explanations/infrastructure-explanation.md` if reset/reindex commands or Milvus usage change.
- [x] Update `docs/plans/0 - project overview.md` processed JSON draft and phase summary when implementation starts or completes.
- [x] Update README only if the user-facing product description or quick-start/reset flow changes.

## Verification Plan

### Automated Tests

- [x] Analysis provider tests validate the new top-level schema.
- [x] Analysis provider tests prove deterministic transcript/source fields cannot be overwritten by LLM output.
- [x] Citation normalization tests prove `seg-*` references map to canonical citations.
- [x] Citation verifier tests reject unknown segments and invalid time ranges.
- [x] Participant registry tests cover attendees, mentioned-only people, speaker-label mapping, role extraction, and participant count facts.
- [x] Speaker stats tests cover segment counts, talk time, and mapped participant IDs.
- [x] Fact extraction tests cover participant count, dates, deadlines, owners, statuses, amounts, and explicit unsupported claims.
- [x] Event extraction tests cover event type, participants, entities, time ranges, statuses, and citations.
- [x] Entity extraction tests cover aliases and mention citations.
- [x] Relationship validation tests reject missing endpoints and preserve valid graph edges.
- [x] Topic summary tests cover parent/child topic links, citation grounding, and rollup summaries.
- [x] Processing pipeline validation tests enforce required sections and reference integrity.
- [x] Retrieval chunk builder tests cover every new chunk type and metadata field.
- [x] Retrieval search tests prove exact participant/count/event/action/owner/deadline questions pin the intended chunk types.
- [x] Chat service tests prove factual answers come from facts or canonical records, not only summary prose.
- [x] Chat service tests prove ambiguous or unsupported questions return partial or not-enough-evidence states.
- [x] Reindex script tests or smoke checks cover new-schema rebuild and obsolete-schema failure.
- [x] Run the backend unittest suite.
- [x] Run the frontend TypeScript/Vite production build if frontend labels or rendering paths change.

### Manual Verification

- [x] Process a transcript with two speakers and explicit names; verify speaker count, participant registry, participant count fact, and citations.
- [x] Process voice-derived transcript evidence with generic speaker labels; verify speaker count works even when names are unknown.
- [x] Ask: "Cuộc gọi này có bao nhiêu người tham gia?" and confirm the answer distinguishes speaker count and identified participants.
- [x] Ask: "Ai đã tham gia cuộc gọi?" and confirm attendees are not mixed with mentioned-only people.
- [x] Ask: "Những sự kiện chính đã xảy ra là gì?" and confirm the answer cites event records and transcript ranges.
- [x] Ask: "Ai chịu trách nhiệm việc tiếp theo?" and confirm the answer uses action records when present.
- [x] Ask: "Deadline là khi nào?" and confirm normalized date/deadline facts are used when present.
- [x] Ask a broad summary question and confirm topic/executive summaries are preferred over isolated transcript chunks.
- [x] Inspect the result drawer and citation UI for facts, participants, events, entities, topics, and transcript windows.
- [x] Delete/rebuild Milvus vectors and confirm retrieval can be rebuilt from `result_json`.

### Acceptance Criteria

- [x] `meeting_intelligence_results.result_json` is the only authoritative meeting knowledge source.
- [x] PostgreSQL `meeting_chunks` and Milvus vectors are fully rebuildable from the new JSON.
- [x] New processed meetings persist the RAG-first `meeting-intelligence-result.v1` schema.
- [x] Participant count, speaker count, attendee list, mentioned-only people, and unknown participants are represented distinctly.
- [x] Facts, events, entities, relationships, actions, decisions, risks, questions, topics, summaries, and citations are all queryable through retrieval chunks.
- [x] Every important extracted record has valid citation evidence or an explicit derived/inferred source.
- [x] Specific factual questions retrieve exact facts or canonical records before summaries or transcript windows.
- [x] Broad questions retrieve topic and executive summaries with supporting evidence.
- [x] Chat answers cite transcript-backed evidence and avoid unsupported claims.
- [x] Old local schema data is reset, rejected, or reprocessed rather than silently indexed with stale assumptions.
- [x] Backend, worker, frontend, and documentation accurately describe the new RAG-first intelligence flow.

---

## Completion Report

> **Completed at:** 2026-07-10
> **Verified by:** Manual verification review for meeting `078dd37f-3a73-42d0-83bb-208dba9778fa`, backend unittest discovery in the backend container (`213` tests), targeted schema/retrieval/chat tests, rebuild-script schema guard smoke check, frontend production build, and healthy backend/worker containers

### What was implemented

- Replaced the runtime intelligence JSON contract with a RAG-first `meeting-intelligence-result.v1` shape centered on transcript evidence, canonical citations, speaker stats, participants, entities, facts, events, relationships, topics, summaries, actions, decisions, risks, questions, quality, and extraction metadata.
- Updated `LLMAnalysisProvider` to preserve deterministic transcript/source/evidence/speaker fields, request candidate RAG-first records, normalize citations, derive participant-count facts from speakers, link speaker labels to participants, and mark unsupported claims without evidence or deterministic sources.
- Updated processing validation for required Phase 22 sections, citation/segment integrity, relationship endpoints, and topic references.
- Rebuilt retrieval chunk generation around RAG-first chunk types such as `fact.participant_count`, `speaker.stats`, `participant.profile`, `event.timeline`, `relationship.edge`, `topic.summary`, `action.item`, `decision.record`, `risk.record`, `question.record`, and `transcript.window`.
- Updated retrieval intent pinning, agent tool section types, frontend result section ordering, transcript `speakerLabel` mapping, citation labels, and local reindex obsolete-schema rejection.
- Updated backend, worker, frontend, infrastructure, and overview docs.

### What was changed from original plan

- Semantic entailment verification was implemented as deterministic reference/evidence validation and unsupported-claim marking, not as a separate model-based verifier.
- Manual verification found one retrieval ranking gap: a nationality/citizenship fact existed in JSON and chunks but was not prioritized for a Vietnamese nationality question. Retrieval intent pinning and pinned chunk relevance sorting now promote citizenship/nationality facts before broader participant chunks.
- The reviewed meeting produced no relationship, risk, or question records because that transcript did not support those records; schema support, chunk construction, validation, retrieval pinning, and tool coverage for those sections are verified by automated tests.

### Notes for future sessions

- Phase 22 intentionally breaks the previous `meeting-intelligence-result.v1` runtime contract.
- Do not treat Milvus vectors as source of truth; they must remain rebuildable from `meeting_intelligence_results.result_json`.
- Do not let LLM output overwrite deterministic transcript, source, speaker, or citation fields.
- Old local processed JSON must be reprocessed or reset before running `backend.scripts.rebuild_retrieval_index`.
- Agentic RAG iteration, context, rate-limit, concurrency, task-guard, and circuit-breaker settings are passed from `.env` through Compose to backend/worker; provider circuit breakers consume the configured thresholds and recovery window.
- Meeting deletion now requires successful Milvus vector cleanup before deleting PostgreSQL meeting/chunk rows; vector cleanup failures return a retryable `503` and do not leave new orphan vectors.
- Meeting deletion now requires successful queue revoke before deleting meeting data; queue revoke failures return a retryable `503` and preserve the meeting.
- Added a dry-run-first MinIO orphan cleanup command and removed the currently detected unreferenced objects.
- Phase 1 backend cleanup standardized internal Agentic RAG imports on `backend.services.agent.*`; legacy service module paths remain compatibility wrappers.
- Phase 2 processing refactor started by moving pipeline timing and asset/job observability helpers into `backend.services.processing.observability`; processing order and transaction behavior remain unchanged.
- Phase 2 also moved voice-stage event emission into `backend.services.processing.voice_events`; the pipeline remains the orchestration entrypoint and all `213` backend tests pass.
- Phase 2 moved RAG-first result validation and voice quality warning normalization into `backend.services.processing.result_validation`; the pipeline no longer owns those pure-data helpers.
- Result-validation hardening now quarantines malformed or unknown LLM relationship endpoints with quality warnings and creates a transcript-grounded executive-summary fallback when the model returns an empty summary; the affected meeting was reprocessed successfully.
- Meeting and account deletion now remove associated operational-log events after the authoritative database commit, so deleted/test meetings do not remain in the admin log groups.
- Phase 2 extracted `TranscriptionStage` and `AnalysisStage`; persistence and retrieval-index stages remain coordinated by the pipeline for the next refactor slice.
- Phase 2 extracted `PersistenceStage` and `RetrievalIndexStage`; the processing pipeline now owns stage ordering, transaction boundaries, status transitions, and failure recovery while stage modules own their local orchestration and events.
- Phase 3 extracted Agentic RAG tool contracts and chunk serialization into `backend.services.agent.tool_definitions`, and moved the stable 11-tool catalog into `backend.services.agent.tool_catalog`; `AgentToolRegistry` remains the runtime lookup/dispatch boundary. Legacy registry exports remain available for import compatibility, and all `213` backend tests pass.
- Phase 3 also introduced `backend.services.agent.tool_executor` for retrieval and synthesis implementations. The registry delegates execution to the injected executor while preserving repository overrides used by existing callers and tests; all `213` backend tests pass.
- Phase 3 removed the duplicated retrieval/synthesis handlers from `AgentToolRegistry`; the registry is now limited to catalog lookup, LLM schema formatting, dispatch, and compatibility exports.
- Phase 3 extracted Agentic RAG and synthesis prompt construction plus the stable `Đang tìm bằng chứng trong cuộc họp...` retrieval status copy into `backend.services.agent.prompt_builder`; legacy private imports remain available through `service.py` and all `213` backend tests pass.
- Phase 3 extracted chunk normalization, context conversion, participant-attribute search enforcement, evidence/confidence normalization, fallback formatting, and elapsed-time calculation into `backend.services.agent.response_utils`; legacy private helper imports remain available through `service.py` and all `213` backend tests pass.
- Phase 3 moved the `AgentResult` response DTO into `backend.services.agent.result_models`; `service.py` continues to re-export it for compatibility and all `213` backend tests pass.
- Phase 3 extracted the Think/Execute boundary into `backend.services.agent.agent_loop`; `AgenticRAGService` keeps compatibility wrappers for `_think` and `_execute_tools`, while the new component owns LLM decision normalization and parallel tool execution. All `213` backend tests pass.
- Phase 3 extracted context accumulation, deduplication, token-budget accounting, tool-call summaries, and chunk metadata serialization into `backend.services.agent.context_coordinator`; `AgenticRAGService` keeps compatibility wrappers and all `213` backend tests pass.
- Phase 3 extracted decision synthesis, context synthesis, local-summary fallback, and direct retrieval fallback into `backend.services.agent.answer_synthesizer`; `AgenticRAGService` remains the lifecycle boundary with compatibility wrappers and all `213` backend tests pass.
- Phase 4 extracted retrieval chunk text/metadata formatting into `backend.services.retrieval.chunk_text`, moved the `RetrievedChunk` contract into `backend.services.retrieval.models`, and moved vector/PostgreSQL candidate resolution, intent pinning, and rerank coordination into `backend.services.retrieval.candidate_service`. `RetrievalSearchService` remains the query lifecycle/metadata boundary and all `213` backend tests pass.
- Phase 5 extracted provider contracts into `llm_contracts`, `analysis_contracts`, `guardrail_contracts`, and `voice_contracts`. Existing provider modules remain compatibility entrypoints for concrete adapters and factories; provider-focused tests pass `42/42` and the full backend suite passes `213/213`.
- Phase 6 verification confirmed valid Compose configuration, matching `.env` and `.env.example` key sets, the dry-run-first MinIO orphan cleanup command, the retrieval rebuild command, and a clean full backend suite at `213/213`.
- Follow-up cleanup item 1 removed the retrieval dependency inversion: `retrieval_candidate_service` now receives its scoring policy through `RetrievalScoring` instead of importing private helpers from `retrieval_search_service`; targeted retrieval/indexing tests pass `16/16`.
- Follow-up cleanup item 2 moved retrieval implementations into `backend.services.retrieval` with top-level compatibility wrappers, moved provider contracts into `backend.providers.contracts`, and grouped LLM, voice, and analysis adapters under provider packages.
- Follow-up cleanup item 3 removed the six Agent compatibility wrapper files and moved backend tests into `agent`, `api`, `processing`, `providers`, `retrieval`, and `integration` groups. Full backend discovery remains `213/213` and frontend production build passes.
- Follow-up cleanup item 4 moved large provider entrypoints into canonical `backend.providers.llm`, `backend.providers.voice`, and `backend.providers.analysis` packages, with `backend.providers.contracts` holding shared contracts. The remaining provider wrappers were removed in follow-up item 8 after repository-wide callers migrated.
- Follow-up cleanup item 5 completed the retrieval package migration: all internal/tests/docs imports now use `backend.services.retrieval.*`, and the six top-level retrieval wrapper files were removed. Full backend discovery remains `213/213`.
- Follow-up cleanup item 6 completed provider package restructuring: LLM adapters are under `backend.providers.llm` with shared transport helpers, analysis under `backend.providers.analysis`, voice under `backend.providers.voice`, and shared contracts under `backend.providers.contracts`. Provider-focused tests and full backend discovery pass `213/213`.
- Follow-up cleanup item 7 removed the four flat provider contract wrappers; there are no remaining internal imports from `backend.providers.*_contracts`.
- Follow-up cleanup item 8 removed the remaining three provider compatibility wrappers; all repository imports now resolve through canonical `backend.providers.llm`, `backend.providers.voice`, and `backend.providers.analysis` packages.
- Current documentation now reflects the completed refactor: the backend, worker, and repository maps use canonical package paths, and no removed Agent, retrieval, provider, or contract wrapper is documented as an active runtime entrypoint.
- Follow-up cleanup item 9 completed the test layout refactor: all `24` test modules now live under the six responsibility groups `agent`, `api`, `processing`, `providers`, `retrieval`, and `integration`; only shared `fakes.py` remains at the test root. Unittest discovery from `backend/tests` passes `213/213`.
- Final runtime cleanup completed the Docker/Compose, script, and artifact audit: all declared services/volumes are used, only the active retrieval rebuild and MinIO orphan-cleanup scripts remain, and generated Python/frontend artifacts were removed without deleting named volumes.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/explanations/frontend-explanation.md` if frontend citation labels or rendering assumptions change
- [x] `docs/explanations/infrastructure-explanation.md` if reset/reindex commands or Milvus behavior change
- [x] `docs/plans/0 - project overview.md`
