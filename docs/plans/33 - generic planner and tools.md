# Phase 33 - Generic Planner and Tools

## Status: Done

## Objectives

1. Let planner and tools select canonical records by type/subtype.
2. Keep specialized tools as convenience wrappers, not the system's schema boundary.
3. Make future LLM subtypes queryable without adding a new backend tool.

## Tasks

- [x] Add canonical record type/subtype selectors to query plans.
- [x] Add generic `search_records` tool.
- [x] Filter generic records by type, subtype, query, and bounded limit.
- [x] Preserve specialized retrieval tools for common UX intents.
- [x] Update evidence verifier required-field matching to inspect generic record payloads.
- [x] Expose selectors through `QueryPlan.to_dict()` for agent events and downstream consumers.

## Verification Plan

- [x] Query planner selector tests.
- [x] Tool registry/executor tests for generic record search in container.
- [x] Full agent planner/verifier test suite (`48 tests OK`).

## Acceptance Criteria

- [x] Participant count resolves through `record_type=fact`, `subtype=participant_count`.
- [x] Unknown concepts can be queried through `record_type=observation`.
- [x] Planner and verifier no longer require a hardcoded section for every answer type.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** container planner/tool/verifier suite (`48 tests OK`)

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`

## Related Docs

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
