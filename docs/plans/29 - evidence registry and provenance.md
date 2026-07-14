# Phase 29 - Evidence Registry and Provenance

## Status: Done

## Objectives

1. Establish one evidence item model for transcript, structured, derived, and source provenance.
2. Make retrieval resolve evidence through the central evidence registry.
3. Prepare the reducer cutover from citation-specific links to generic evidence references.

## Tasks

### Evidence contract

- [x] Add canonical evidence kinds and a normalized evidence-item builder.
- [x] Preserve transcript segment IDs and playback time ranges as optional location metadata.
- [x] Support structured and derived evidence without inventing transcript timestamps.
- [x] Add evidence lookup by ID for downstream services.

### Consumers

- [x] Make retrieval citation lookup resolve the central evidence collection.
- [x] Change hierarchical reducer output from the old citation collection to `evidence.items`.
- [x] Replace record `citationIds` with `evidenceRefs` and `sourceWindowIds` with `sourceRefs` in the reducer and validator.
- [x] Validate evidence references and source-window references before persistence.

## Verification Plan

### Automated Tests

- [x] `python3 -m unittest backend.tests.knowledge.test_evidence backend.tests.knowledge.test_semantic_registry`
- [x] Run `docker compose exec -T backend python -m unittest backend.tests.processing.test_processing_pipeline_service backend.tests.retrieval.test_retrieval_index_service`.
- [x] Host-only retrieval tests were run in the project container because SQLAlchemy is not installed in the host interpreter.

### Acceptance Criteria

- [x] Retrieval can resolve evidence from the central evidence registry.
- [x] Every hierarchical reducer record points only to valid evidence/source references.
- [x] Structured facts have no fabricated playback timestamps.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** knowledge contract tests, compile validation, and container processing/retrieval tests (`6 tests OK`)

### What was implemented

- Added canonical evidence item kinds and lookup helpers.
- Switched hierarchical reducer output to `evidence.items` and v2 provenance references.
- Updated unified-result validation and retrieval mapping to use the new references.

### Notes for future sessions

- The non-hierarchical provider's local candidate payload still uses internal citation IDs; it is normalized at the reducer boundary and is removed in the provider contract phase.

## Related Docs

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
