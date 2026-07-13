# Phase 25 - Codex-Style Hierarchical Intelligence Extraction

## Status: Done

## Objectives

1. Prevent transcript length from exceeding a single LLM context window.
2. Persist retryable extraction windows without duplicating the full transcript.
3. Replace flat intelligence arrays with unified, citation-backed knowledge records.
4. Keep PostgreSQL authoritative and Milvus derived for retrieval.

## Tasks

### 1. Windowing And Persistence

- [x] Add deterministic token-bounded transcript window creation.
- [x] Preserve speaker-turn boundaries, timestamps, ordered segment IDs, and overlap.
- [x] Add configurable target tokens, hard limit, overlap, and bounded workers.
- [x] Add `meeting_transcript_windows` model and Alembic migration.
- [x] Persist window status, attempts, hashes, local extraction JSON, and errors.
- [x] Attach completed windows to the canonical intelligence result.

### 2. Hierarchical Intelligence Contract

- [x] Keep the `meeting-intelligence-result.v1` identifier.
- [x] Replace flat canonical arrays with `knowledge.records` and `knowledge.relationships`.
- [x] Preserve full transcript and add a transcript window manifest.
- [x] Preserve deterministic speakers, evidence citations, summaries, quality, and extraction metadata.
- [x] Add `sourceWindowIds` and normalized citation references to global records.

### 3. Bounded Extraction And Reduction

- [x] Run LLM extraction per bounded window instead of sending the full transcript.
- [x] Persist local extraction results per window.
- [x] Fan out bounded local calls and reduce results deterministically into global records.
- [x] Merge duplicate records and preserve all citations/source windows.
- [x] Remap local citation IDs to canonical full-transcript citation IDs.
- [x] Aggregate local summaries into a bounded executive summary.
- [x] Record extraction generation, window count, coverage, and warnings.
- [x] Add retryable Celery extraction task for individual windows.

### 4. Validation And Retrieval

- [x] Validate unified records, citation IDs, window references, and relationship endpoints.
- [x] Keep legacy validation available for existing provider/test fixtures.
- [x] Adapt retrieval chunk building to unified records through a canonical compatibility view.
- [x] Keep PostgreSQL chunks authoritative and Milvus vectors derived.
- [x] Update retrieval rebuild schema detection for the unified result shape.

### 5. API And Frontend

- [x] Keep the public intelligence endpoint free of raw local extraction artifacts.
- [x] Map unified records to existing frontend intelligence sections.
- [x] Preserve transcript playback and citation rendering.
- [x] Keep extraction/retrieval logic out of the frontend.

### 6. Verification

- [x] Add bounded-window and overlap unit coverage.
- [x] Add pipeline coverage for persisted windows and unified records.
- [x] Run Alembic upgrade to the new head.
- [x] Run full backend unittest discovery (`229/229`).
- [x] Run frontend typecheck and production build.
- [x] Run `docker compose config --quiet`.

## Verification Plan

### Automated Tests

- [x] `docker compose exec -T backend python -m unittest discover -s backend/tests -p 'test_*.py'`
- [x] `npm run build` in `frontend/`
- [x] `docker compose config --quiet`
- [x] `docker compose exec -T backend alembic upgrade head`

### Acceptance Criteria

- [x] A long transcript is processed through bounded windows rather than one full-transcript LLM prompt.
- [x] Full transcript remains recoverable in the canonical result.
- [x] Each global record links to citations and source windows.
- [x] Window failures can be retried independently.
- [x] Retrieval continues to use PostgreSQL fallback and derived Milvus vectors.
- [x] Existing frontend intelligence sections remain renderable.

---

## Completion Report

> **Completed at:** 2026-07-13
> **Verified by:** Alembic migration, backend unittest discovery (`229/229`), frontend production build, and Compose validation

### What was implemented

- Added bounded transcript windows with overlap, hashes, configurable token limits, and PostgreSQL processing state.
- Added unified `knowledge.records`/`knowledge.relationships` canonical JSON generation while keeping the v1 identifier.
- Added bounded parallel local extraction, global reduction, citation remapping, and retryable window task wiring.
- Updated validation, retrieval indexing, rebuild detection, frontend rendering, runtime configuration, and explanation docs.

### Notes for future sessions

- Existing local meetings with the previous JSON shape must be reprocessed before retrieval rebuild.
- Local extraction artifacts are internal PostgreSQL state; the public intelligence response exposes canonical global records and window references only.
- Milvus remains a rebuildable derived vector index.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
- [x] `docs/plans/25 - codex-style hierarchical intelligence extraction.md`
