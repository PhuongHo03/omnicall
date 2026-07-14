# Phase 37 - Database Reset and V2 Cutover

## Status: Done

## Objectives

1. Remove obsolete local v1 intelligence artifacts because v1 compatibility is explicitly out of scope.
2. Reprocess every meeting through the v2 hierarchical pipeline.
3. Rebuild PostgreSQL chunks and Milvus vectors from v2 JSON only.

## Tasks

- [x] Add an explicit dry-run/reprocess script for local v2 cutover.
- [x] Delete old chat, chunks, results, and vectors within meeting scope.
- [x] Reset meetings to `QUEUED` and enqueue idempotent processing tasks.
- [x] Execute the cutover for all processable local meetings (`queued_v2_reprocessing=3`).
- [x] Verify every result row has schema v2 and evidence items.
- [x] Verify every retrieval chunk generation points to a v2 result.

## Verification Plan

- [x] `python -m backend.scripts.reprocess_all_meetings_v2 --dry-run`.
- [x] Run the script without `--dry-run` in the local runtime.
- [x] Poll worker completion and inspect failed meeting diagnostics.
- [x] Run retrieval rebuild/search smoke tests after completion.

## Acceptance Criteria

- [x] No local meeting result remains on v1.
- [x] No stale v1 chat citation remains; chat history was cleared during cutover.
- [x] PostgreSQL and Milvus indexed vectors are derived from the 3 processable v2 results; generation smoke checks match PostgreSQL chunk metadata.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** `backend.scripts.verify_v2_cutover` — 4 meetings, 3 processable, 3 v2/READY results, 196 chunks, 0 orphan chunks.

### Notes for future sessions

- One local meeting had no uploaded asset and was accidentally queued by the first version of the migration script. It was restored to `DRAFT`; the script now filters by `MeetingAsset` before enqueueing.

## Related Docs

- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/plans/0 - project overview.md`
