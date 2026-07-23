# Phase 40 - Generic query graph and answer projections

## Status: Done

## Objectives

Make JSON v2 questions resolve through one generic record query contract with identity-aware participant data, relationship selectors, temporal selectors, verifier coverage, and deterministic answer projections.

## Tasks

### Query graph contract
- [x] Add `relationTypes` and `answerShape` to query plans and replans.
- [x] Preserve record selectors through replanning.
- [x] Support generic record type/subtype/relation/answer-shape parameters in `search_records`.
- [x] Normalize Vietnamese `đ` so planner capability matching works for all Vietnamese phrases.

### Identity and relationships
- [x] Store speaker profiles and speaker counts as v2 records.
- [x] Preserve actor/target fields as searchable record fields.
- [x] Resolve participant-list, actor-target, location, count, and timeline projections without specialized tools.

### Verification and synthesis
- [x] Verify required relation capabilities in addition to record fields.
- [x] Add deterministic projections for common generic answer shapes.
- [x] Add persisted identity-resolution relationships between named participants and speaker labels where evidence supports the link.

## Verification Plan

- [x] Agent tests pass (`119 tests OK`).
- [x] Planner smoke tests cover participant, count, timeline, actor-target, and location questions.
- [x] Meeting `4a70293b-d8de-4521-a165-7659d80beb9b` record/tool smoke checks cover participants, count, actor, target, and location.
- [x] Rebuild/reprocess all runtime meetings with the final query-graph reducer and validate persisted identity relationships. Both processable meetings are `READY` with v2 results and identity-resolution relationships.

## Completion Report

> **Completed at:** 2026-07-15
> **Verified by:** Full local reprocess plus `python -m backend.scripts.verify_v2_cutover`.

### What was implemented

- Generic record/relation query planning, verification, deterministic projections, and persisted identity-resolution relationships.

### What was changed from original plan

- The formerly failed local meeting reprocessed successfully; no exception remains for the runtime verification scope.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`

### Runtime verification

- `verify_v2_cutover` reports `meetings=2`, `processable=2`, `v2Results=2`, `chunks=153`, `identityRelationships=2`, `orphanChunks=[]`, and `failures=[]`.
