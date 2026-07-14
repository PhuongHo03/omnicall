# Phase 40 - Generic query graph and answer projections

## Status: In Progress

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
- [ ] Rebuild/reprocess all runtime meetings with the final query-graph reducer and validate persisted identity relationships. **Blocked for meeting `fa753516-986f-4b18-b528-bcc60c750439`: the local transcription pipeline ends in `FAILED` before persisting a v2 result; meeting `4a70293b-d8de-4521-a165-7659d80beb9b` is `READY` and verified with one persisted `identity_resolution` relationship.**

## Completion Report

> **Completed at:** pending one runtime meeting whose transcription pipeline fails before v2 persistence

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`

### Runtime verification

- `verify_v2_cutover` currently reports `v2Results=1`, `identityRelationships=1`, and no orphan chunks.
- The remaining meeting has no persisted result because the worker fails during the transcription pipeline; the worker now logs the original exception and stage for the next retry.
