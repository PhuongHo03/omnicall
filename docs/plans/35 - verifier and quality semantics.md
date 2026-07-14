# Phase 35 - Verifier and Quality Semantics

## Status: Done

## Objectives

1. Verify generic records by canonical type and payload fields.
2. Keep evidence sufficiency independent of hardcoded section names.
3. Preserve specialized intent checks without coupling them to the data model.

## Tasks

- [x] Match evidence relevance by planner record type selectors.
- [x] Inspect generic record metadata/payload fields in required-field checks.
- [x] Add generic metadata/payload field matching; subtype-specific questions use the same canonical selector boundary.
- [x] Add representative direct, derived, and unsupported evidence fixtures; the same JSON contract is source-kind agnostic.

## Verification Plan

- [x] Agent planner/verifier suite in container after rebuild (`48 tests OK`).
- [x] Evaluation matrix for direct, derived, and unsupported claims.

## Acceptance Criteria

- [x] Generic observation/fact records can satisfy verifier relevance.
- [x] Required fields are not tied only to section labels.
- [x] Evidence state remains correct for the covered planner/verifier question families.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** container planner/tool/verifier suite (`48 tests OK`)

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`

## Related Docs

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
