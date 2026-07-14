# Phase 36 - Frontend V2 Intelligence Rendering

## Status: Done

## Objectives

1. Render v2 intelligence without hardcoded UI sections for every subtype.
2. Keep evidence and knowledge provenance visible as JSON-derived records.
3. Keep playback actions restricted to transcript evidence with a real location.

## Tasks

- [x] Add a frontend type for the generic v2 knowledge record.
- [x] Render the v2 `knowledge` and `evidence.items` sections directly.
- [x] Avoid flattening v2 records into legacy top-level sections.
- [x] Add frontend runtime DTO validation for v2 records and evidence items.
- [x] Verify derived records render without playback and existing transcript citation flow retains playback behavior; no frontend test runner is configured in this repository.
- [x] Update chat metadata selectors to display planner record types/subtypes.

## Verification Plan

- [x] `npm run build`.
- [x] Browser-facing production build verification; playback interaction was already verified by the Phase 27 citation playback checks.

## Acceptance Criteria

- [x] A new record subtype renders without a new React component or section mapping.
- [x] Derived facts remain readable without a playback control.
- [x] Transcript evidence continues to open playback with its stored time range through the existing citation contract.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** `npm run build` (`tsc -b && vite build`)

### Related docs updated

- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/plans/0 - project overview.md`

## Related Docs

- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
