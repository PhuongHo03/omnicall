# Phase 38 - Evaluation, Operations, and Completion

## Status: Done

## Objectives

1. Verify the generalized v2 contract across direct, derived, and unsupported answers.
2. Document operational reset/reprocess behavior and known data exceptions.
3. Close the migration with reproducible backend/frontend/runtime checks.

## Tasks

### Evaluation

- [x] Add direct transcript evidence fixture.
- [x] Add derived structured fact fixture without playback location.
- [x] Add unsupported-claim fixture that remains insufficient.
- [x] Run representative direct/derived/unsupported evidence matrix; all 3 fixtures pass.

### Operations

- [x] Document `reprocess_all_meetings_v2 --dry-run` and destructive scope.
- [x] Document worker schema propagation and v2 result verification.
- [x] Add `backend.scripts.verify_v2_cutover` for processable meeting/result/chunk consistency.

### Final verification

- [x] Full backend test discovery in a container with test-only rate-limit override: `270 tests OK`.
- [x] Frontend production build.
- [x] Python compile and `git diff --check`.
- [x] Verify all processable meetings are READY with v2 results; one orphan meeting without an asset is explicitly excluded.

## Acceptance Criteria

- [x] Every processable local meeting has one v2 result and v2-derived chunks.
- [x] Generic record types/subtypes work without new tools or UI components.
- [x] Direct evidence has playback location; derived evidence does not fabricate one.
- [x] Final docs and phase overview have no stale v1 runtime claims.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** v2 health command, 270-test discovery, 3 evidence fixtures, frontend build, compile validation, and diff check.

### Notes

- The normal runtime quota causes six API fixture failures when the suite is run repeatedly in one process; with `RATE_LIMIT_ENABLED=false` for tests, the complete suite passes `270 tests OK`. Production rate limiting remains enabled.

## Related Docs

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/plans/0 - project overview.md`
