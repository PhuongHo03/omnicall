# Phase 32 - Generic Retrieval and Record Indexing

## Status: Done

## Objectives

1. Index all canonical knowledge records, including unknown observations, through generic retrieval paths.
2. Keep structured record evidence separate from transcript evidence.
3. Avoid adding a new retrieval section for every LLM subtype.

## Tasks

- [x] Map v2 records to retrieval inputs through canonical type.
- [x] Add generic `observation.record` indexing fallback.
- [x] Preserve subtype in indexed record text/metadata.
- [x] Resolve evidence through the central evidence registry.
- [x] Replace the legacy-named flat-section adapter with the v2-only `_canonical_record_view`; it is an internal index projection, not a v1 compatibility path.
- [x] Add and execute the v2 reprocess/reindex migration for all processable existing meetings.

## Verification Plan

- [x] Add generic observation retrieval-view test.
- [x] Run full retrieval/index/search tests in container; targeted retrieval/index suite passed and full discovery executed.
- [x] Rebuild PostgreSQL chunks and Milvus vectors after v2 cutover; 196 chunks point to v2 results.

## Acceptance Criteria

- [x] Unknown records remain searchable as `observation.record`.
- [x] Subtypes do not create unregistered retrieval sections.
- [x] Every indexed chunk carries canonical source/evidence provenance or a deterministic JSON record source ID.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** v2 cutover SQL verification and container retrieval tests

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`

## Related Docs

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
