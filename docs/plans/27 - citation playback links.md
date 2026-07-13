# Phase 27 - Citation Playback Links

## Status: In Progress

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
- [x] Rebuild and repair citation history for meeting `8a7eab47-c4dc-4d03-92e3-85cd59dfd904`.

### Frontend citation UI

- [x] Map the new citation contract and accept legacy citation records.
- [x] Rename the badge to `Citations (n)`.
- [x] Count unique citation IDs.
- [x] Render quote, section, source kind, JSON pointer, and time range.
- [x] Hide playback action for citations without transcript location metadata.

### Playback and transcript integration

- [x] Pass citation seek requests from chat to the playback drawer.
- [x] Seek to citation `startMs` when available.
- [x] Focus the matching transcript segment when `segmentIds` are available.
- [x] Fall back from segment lookup to timestamp seeking.
- [ ] Add browser-level verification for audio and video citation seeking.

### Tests and documentation

- [ ] Add backend citation extraction, deduplication, verifier, and legacy-history tests.
- [ ] Add frontend DTO, badge, structured-citation, and playback interaction tests.
- [x] Run frontend TypeScript/Vite build.
- [x] Run Python compile validation.
- [x] Update backend and frontend explanations.
- [x] Update project overview and Phase 27 plan.

## Verification Plan

### Automated Tests

- [ ] Backend targeted chat/agent tests.
- [ ] Backend full test discovery.
- [x] Frontend TypeScript/Vite build.
- [x] Python compile validation.
- [ ] `git diff --check`.

### Manual Verification

- [ ] Verify badge count equals unique verified citations.
- [x] Verify transcript citation seeks to the expected playback position using persisted meeting data.
- [ ] Verify transcript segment focus/highlight.
- [ ] Verify structured citations remain readable without playback controls.
- [ ] Verify old persisted chat history remains readable.

### Acceptance Criteria

- [ ] The UI displays `Citations (n)`, not `Sources (n)`.
- [ ] Unverified citation IDs never reach the UI.
- [ ] Citation count is independent of retrieved chunk count.
- [ ] Transcript citations link to playback when location data exists.
- [ ] Structured citations do not expose broken playback actions.
- [ ] Existing chat history remains compatible.

## Completion Report

> **Completed at:** Pending
> **Verified by:** Pending

### Notes for future sessions

- The current workspace already contains broad Phase 26 refactor changes. Preserve unrelated worktree changes.
- Backend dependencies are not installed in the current environment, so Python unit tests require the project runtime/container.

## Related Docs

- [x] `docs/plans/0 - project overview.md`
- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
