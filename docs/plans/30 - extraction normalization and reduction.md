# Phase 30 - Extraction Normalization and Reduction

## Status: Done

## Objectives

1. Normalize every provider/window candidate into the v2 knowledge record envelope.
2. Keep subtype-specific fields in `data` while making canonical type selection deterministic.
3. Ensure derived facts do not inherit unrelated transcript evidence.

## Tasks

- [x] Add one normalization boundary for window candidates.
- [x] Map known extraction sections to canonical record types.
- [x] Preserve unknown concepts as `observation` records.
- [x] Preserve subtype and provider fields inside record data.
- [x] Reduce duplicate records by stable ID while merging provenance and confidence.
- [x] Keep deterministic speaker-derived facts free of fabricated transcript evidence.
- [x] Provider window candidates remain an internal extraction input and are normalized immediately into v2; no provider candidate fields are persisted.

## Verification Plan

- [x] `python3 -m unittest backend.tests.knowledge.test_normalization backend.tests.knowledge.test_evidence backend.tests.knowledge.test_semantic_registry`
- [x] Container processing and retrieval tests after reducer integration.
- [x] Add focused tests for unknown and subtype-rich provider candidates.

## Acceptance Criteria

- [x] All hierarchical records entering persistence use canonical `type` and v2 provenance fields.
- [x] No unknown LLM type creates a new downstream section.
- [x] Derived records do not receive unrelated transcript locations.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** 11 knowledge tests, compile validation, and container processing/retrieval tests

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
