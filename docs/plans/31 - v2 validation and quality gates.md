# Phase 31 - V2 Validation and Quality Gates

## Status: Done

## Objectives

1. Reject malformed generalized intelligence before it reaches PostgreSQL or retrieval.
2. Make provenance and playback behavior explicit in validation.
3. Prevent cross-record and cross-meeting reference corruption.

## Tasks

- [x] Validate v2 record envelope fields and canonical types.
- [x] Validate unique evidence IDs and transcript segment references.
- [x] Validate evidence/source references from knowledge records.
- [x] Reject transcript locations on structured/derived evidence.
- [x] Add focused v2 validation tests.
- [x] Add focused validation diagnostics through explicit error messages; taxonomy expansion remains a later quality-evaluation task.

## Verification Plan

- [x] `python3 -m unittest backend.tests.processing.test_v2_result_validation`
- [x] `python3 -m compileall -q backend/services/processing backend/tests/processing`
- [x] Run the full processing pipeline suite in container after v2 reducer integration.

## Acceptance Criteria

- [x] Invalid v2 records fail before persistence.
- [x] Derived facts can be valid without playback timestamps.
- [x] Direct transcript evidence retains segment/time references.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** 3 v2 validation tests, compile validation, and container processing tests

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`

## Related Docs

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
