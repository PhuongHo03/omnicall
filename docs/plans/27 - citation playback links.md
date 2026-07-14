# Phase 27 - Citation Playback Links

## Status: Done

## Objectives

1. Return verified citation-level evidence instead of retrieved chunks as citations.
2. Display a `Citations (n)` badge with deduplicated evidence records.
3. Let transcript citations seek the meeting playback and focus the matching transcript segment.
4. Preserve compatibility with Phase 26 persisted chat history.

## Tasks

### Backend citation contract

- [x] Add canonical `citation_id` and `quote` response fields.
- [x] Track verified citation IDs from answer synthesis.
- [x] Map only verified IDs back to retrieved chunks.
- [x] Deduplicate citation records by citation ID.
- [x] Keep retrieved chunk IDs separate from citation count.
- [x] Normalize legacy `citation_ids` JSONB records when reading history.
- [x] Add canonical quote lookup from processed `evidence.citations` metadata where chunk text is not the direct quote.
- [x] Persist per-citation transcript locations in retrieval chunk metadata.
- [x] Resolve chat response timestamps and segment IDs by citation ID.
- [x] Assign stable JSON citation IDs to derived records without direct transcript citations.
- [x] Prevent derived records from inheriting all transcript citation IDs.
- [x] Keep transcript playback actions limited to evidence with transcript location metadata.
- [x] Rebuild and repair citation history for meeting `8a7eab47-c4dc-4d03-92e3-85cd59dfd904`.

### Frontend citation UI

- [x] Map the new citation contract and accept legacy citation records.
- [x] Rename the badge to `Citations (n)`.
- [x] Count unique citation IDs.
- [x] Render quote, section, source kind, JSON pointer, and time range.
- [x] Hide playback action for citations without transcript location metadata.
- [x] Keep the meeting process action in the same locked `Processing` state for both `QUEUED` and `PROCESSING` meetings.

### Meeting lifecycle feedback

- [x] Reuse `EmptyState` for draft, uploaded, queued, processing, and failed meeting messages.
- [x] Add a feature-local `MeetingProgressBar` for determinate upload and indeterminate processing progress.

### Playback and transcript integration

- [x] Pass citation seek requests from chat to the playback drawer.
- [x] Seek to citation `startMs` when available.
- [x] Focus the matching transcript segment when `segmentIds` are available.
- [x] Fall back from segment lookup to timestamp seeking.
- [x] Verify audio/video citation seek wiring through frontend build and persisted playback-location checks; no browser test runner is configured in this repository.

### Tests and documentation

- [x] Cover citation extraction, deduplication, verifier, structured records, and playback-location behavior through targeted/container tests and v2 evidence fixtures.
- [x] Cover frontend DTO, badge, structured-citation, and playback interaction contracts through TypeScript production build and source-level feature verification; no frontend test runner is configured.
- [x] Run frontend TypeScript/Vite build.
- [x] Run Python compile validation.
- [x] Update backend and frontend explanations.
- [x] Update project overview and Phase 27 plan.

## Verification Plan

### Automated Tests

- [x] Backend targeted chat/agent tests.
- [x] Backend full test discovery (`270 tests OK` with test-only rate-limit override).
- [x] Frontend TypeScript/Vite build.
- [x] Python compile validation.
- [x] `git diff --check`.

### Manual Verification

- [x] Verify badge count equals unique verified citations.
- [x] Verify transcript citation seeks to the expected playback position using persisted meeting data.
- [x] Verify transcript segment focus/highlight through segment-ID playback wiring and persisted citation location checks.
- [x] Verify structured citations remain readable without playback controls.
- [x] Legacy persisted chat history compatibility is no longer required after the approved v2 data reset; current v2 history is rebuilt from the new contract.

### Acceptance Criteria

- [x] The UI displays `Citations (n)`, not `Sources (n)`.
- [x] Unverified citation IDs never reach the UI.
- [x] Citation count is independent of retrieved chunk count.
- [x] Transcript citations link to playback when location data exists.
- [x] Structured citations do not expose broken playback actions.
- [x] Current v2 chat history remains compatible with the v2 contract; v1 history migration is explicitly out of scope.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** frontend build, Python compile/diff checks, targeted/container Agentic RAG tests, full backend discovery, and meeting citation playback verification.

### What changed from original plan

- The original Phase 26 legacy-history compatibility requirement was superseded by the approved v2-only migration decision. Existing local chat history was cleared during the v2 cutover rather than maintained through a v1 adapter.

### Notes for future sessions

- The current workspace already contains broad Phase 26 refactor changes. Preserve unrelated worktree changes.
- Backend dependencies are not installed in the current environment, so Python unit tests require the project runtime/container.
- Failed meetings now render `Retry` from status/list metadata. The action remains disabled when `latest_asset` is absent because backend retry requires a source file; its tooltip explains the missing-asset condition.

## Related Docs

- [x] `docs/plans/0 - project overview.md`
- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
