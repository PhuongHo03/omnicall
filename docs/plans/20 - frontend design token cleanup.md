# Phase 20 - Frontend Design Token Cleanup

## Status: Done

## Objectives

1. Make frontend visual primitives more consistent without changing product workflows.
2. Move reusable color, radius, shadow, overlay, font, and line-height values into shared CSS tokens.
3. Remove avoidable inline style and one-off hard-coded values from frontend UI code.
4. Keep the existing domain CSS split from Phase 19.

## Prerequisites

- [x] Phase 19 frontend CSS split is complete.
- [x] Current design tokens are reviewed in `frontend/src/shared/styles/tokens.css`.
- [x] Current hard-coded style values are scanned before editing.

## Tasks

### 1. Token Expansion

- [x] Add font-family tokens for body and mono text.
- [x] Add line-height tokens for compact, normal, relaxed, and dense text.
- [x] Add radius tokens for common control/card/pill/circle values.
- [x] Add focus-ring, overlay, media, and semantic alpha-color tokens.
- [x] Fix malformed token formatting where multiple custom properties are on one line.

### 2. CSS Cleanup

- [x] Replace repeated hard-coded focus rings and shadows with tokens.
- [x] Replace repeated hard-coded overlay colors with tokens.
- [x] Replace common `border-radius` values with radius tokens where semantic.
- [x] Replace mono font stacks with the mono font token.
- [x] Replace hard-coded success/danger alpha backgrounds with semantic tokens.
- [x] Keep legitimate dynamic or media-specific values such as waveform dimensions and progress widths.

### 3. React Inline Style Cleanup

- [x] Remove avoidable inline color/font-size style from `AppRoutes`.
- [x] Keep runtime inline widths for playback/progress bars because they represent dynamic state.

### 4. Documentation

- [x] Update `docs/explanations/frontend-explanation.md` to document the expanded token contract.
- [x] Update `docs/plans/0 - project overview.md` with Phase 20 status.
- [x] Complete this phase checklist and completion report after verification.

## Verification Plan

### Automated Tests

- [x] `cd frontend && npm run build`
- [x] Scan frontend source for avoidable inline style.
- [x] Scan CSS for remaining high-risk hard-coded color/font values outside documented exceptions.

### Manual Verification

- [x] Source review confirms visual semantics are preserved.
- [x] No route, API, or feature workflow code is changed.

### Acceptance Criteria

- [x] Design tokens cover common typography, radius, focus, overlay, shadow, and semantic alpha colors.
- [x] Domain CSS files use tokens for reusable primitives.
- [x] React code does not contain avoidable static color/font-size inline style.
- [x] Build passes.

---

## Completion Report

> **Completed at:** 2026-07-09
> **Verified by:** `cd frontend && npm run build`, hard-coded style scans outside `tokens.css`, inline-style scan, and source review.

### What was implemented

- Expanded `tokens.css` with shared font-family, line-height, radius, icon-size, overlay, focus-ring, shadow, alpha-color, media, and gradient tokens.
- Replaced reusable hard-coded CSS values across domain styles with tokens.
- Removed the static inline session note style from `AppRoutes` and added token-backed auth note/error classes.
- Updated waveform canvas fallback colors to read from CSS variables instead of hex literals.

### What was changed from original plan

- Runtime progress widths in `PlayerControls` and `TranscriptTrack` intentionally remain inline styles because they are dynamic state.
- The style scan still reports `&#9662;` in `ChatMessageBubble` because the regex sees the HTML entity as a hex-like literal; it is not a color token issue.

### Notes for future sessions

- Keep new reusable visual primitives in `tokens.css` before adding feature CSS hard-codes.
- Prefer token-backed CSS classes over static inline styles in React components.

### Related docs updated

- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/plans/0 - project overview.md` (phase summary table)
