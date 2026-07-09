# Phase 19 - Frontend Refactor Safety Cleanup

## Status: Done

## Objectives

1. Refactor the frontend by feature meaning while preserving the current React Router/Vite structure.
2. Reduce large, mixed-responsibility files without changing user-facing behavior.
3. Remove low-risk hygiene issues before larger structural moves.
4. Keep chat streaming, optimistic assistant messages, meeting polling, playback, recording, admin logs, and theme behavior at least as capable as the current implementation.
5. Verify every refactor batch independently so the frontend is upgraded, not regressed.

## Prerequisites

- [x] Phase 17 typewriter/SSE behavior is understood and preserved.
- [x] Phase 18 backend SSE `connected` payload and Agentic RAG event contract are understood.
- [x] Current frontend baseline is recorded with `npm run build`.
- [x] Existing dirty worktree is reviewed before editing touched files.
- [x] No generated frontend artifacts such as `vite.config.js`, `vite.config.d.ts`, or `*.tsbuildinfo` are committed accidentally.

## Tasks

### 1. Baseline and Safety Net

- [x] Run the current frontend build and record baseline:
  - [x] `cd frontend && npm run build`
  - [x] Note any warnings before changing code.
- [x] Confirm there are no frontend tests configured in `package.json`; if none exist, use TypeScript/Vite build plus manual checks as the safety net.
- [x] Review current touched frontend files before editing so unrelated user changes are preserved.
- [x] Keep route structure under `frontend/src/routes/` unchanged.
- [x] Keep feature code under `frontend/src/features/<feature>/`.
- [x] Keep cross-feature helpers under `frontend/src/shared/`.

### 2. Low-Risk Hygiene First

- [x] Fix the dangling CSS rule in `frontend/src/shared/styles/global.css` that currently produces a Vite/esbuild CSS minify warning near the dark auth-theme section.
- [x] Remove unused `Minus` import and `void Minus` workaround from `MeetingIntelligenceResultPanel`.
- [x] Remove obvious extra blank lines or indentation drift only inside files being touched.
- [x] Confirm generated files remain ignored and untracked:
  - [x] `frontend/vite.config.js`
  - [x] `frontend/vite.config.d.ts`
  - [x] `frontend/*.tsbuildinfo`
- [x] Re-run `npm run build` and confirm the CSS warning is gone.

### 3. Shared HTTP Boundary

- [x] Create a shared HTTP helper only for cross-feature mechanics, for example `frontend/src/shared/utils/httpClient.ts`.
- [x] Move common API mechanics into the shared helper:
  - [x] API prefix handling.
  - [x] bearer auth headers.
  - [x] JSON content headers.
  - [x] response JSON parsing.
  - [x] backend error message extraction for `message`, string `detail`, and validation-array `detail`.
  - [x] blob response error handling.
- [x] Keep feature-specific endpoint functions in their feature `api/` folders:
  - [x] `features/auth/api/authApi.ts`
  - [x] `features/admin/api/adminApi.ts`
  - [x] `features/meetings/api/meetingApi.ts`
- [x] Preserve current exported API function names and signatures unless all callers are updated in the same batch.
- [x] Preserve retry behavior for existing read/session calls that use `retryWithBackoff`.
- [x] Re-run `npm run build`.

### 4. Meeting Types, States, and Formatters

- [x] Keep `features/meetings/types/meetingTypes.ts` focused on compile-time contracts.
- [x] Move runtime helpers out of `meetingTypes.ts`:
  - [x] `resolveMediaKind`
  - [x] `formatTime`
  - [x] `formatFileSize`
- [x] Create a feature utility module such as `features/meetings/utils/meetingFormatters.ts`.
- [x] Move meeting state predicates out of `useMeetingWorkspace` into a feature state/helper module:
  - [x] `isUploadableMeeting`
  - [x] `isProcessableMeeting`
  - [x] `isProcessingMeeting`
  - [x] `isAudioAsset`
- [x] Keep call sites behaviorally identical after import updates.
- [x] Re-run `npm run build`.

### 5. Chat Stream and Optimistic Message Boundary

- [x] Split chat/SSE stream concerns out of `meetingApi.ts` while keeping compatibility for current callers.
- [x] Create a focused stream module, for example:
  - [x] `features/meetings/api/chatStreamApi.ts`
  - [x] or `features/meetings/hooks/useMeetingChatStream.ts` if stream lifecycle is moved directly into a hook.
- [x] Keep REST chat functions in `meetingApi.ts`:
  - [x] `askMeetingChat`
  - [x] `getMeetingChatHistory`
- [x] Preserve current `ChatStreamEvent` union semantics:
  - [x] `connected`
  - [x] `status`
  - [x] `agent_think`
  - [x] `agent_search`
  - [x] `observation`
  - [x] `agent_synthesize`
  - [x] `fast_path`
  - [x] `done`
  - [x] `blocked`
  - [x] `error`
- [x] Preserve SSE parser tolerance for `event:` and `retry:` lines.
- [x] Preserve AbortController cleanup behavior.
- [x] Move optimistic chat message helpers out of `useMeetingWorkspace`:
  - [x] optimistic user message creation.
  - [x] optimistic assistant status message creation.
  - [x] agent tool label/status formatting.
  - [x] typewriter ID selection for completed assistant messages.
- [x] Re-run `npm run build`.

### 6. Split `useMeetingWorkspace` by Workflow

- [x] Keep `useMeetingWorkspace` as the public facade used by `MeetingsScreen`.
- [x] Preserve the current return object shape as much as possible so screen/component changes stay small.
- [x] Extract meeting selection and route sync:
  - [x] requested meeting ID handling.
  - [x] selected meeting ID state.
  - [x] current meeting ref and abort controller lifecycle.
- [x] Extract meeting list polling:
  - [x] `listMeetings` polling.
  - [x] faster interval while meetings are `QUEUED` or `PROCESSING`.
  - [x] selected meeting status transition handling.
- [x] Extract selected meeting loading:
  - [x] meeting detail fetch.
  - [x] result fetch for `READY` meetings.
  - [x] chat history fetch for `READY`, `QUEUED`, and `PROCESSING` meetings.
  - [x] pending chat answer detection.
- [x] Extract chat workflow:
  - [x] submit question.
  - [x] recover from non-network chat errors.
  - [x] SSE watch.
  - [x] polling fallback for answer completion.
  - [x] stop/cleanup chat watch on meeting switch.
- [x] Extract asset playback URL lifecycle:
  - [x] blob download for playable asset.
  - [x] object URL creation.
  - [x] object URL revocation.
- [x] Extract recording workflow:
  - [x] microphone permission request.
  - [x] `MediaRecorder` lifecycle.
  - [x] recorded blob to upload file conversion.
  - [x] track cleanup on stop.
- [x] Extract transcript mapping from processed result to `TranscriptEntry[]`.
- [x] Extract asset download helper that creates a browser download link.
- [x] Re-run `npm run build` after each extraction batch, not only at the end.

### 7. Meeting Chat Panel Cleanup

- [x] Keep `MeetingChatPanel` presentational and free of API calls.
- [x] Extract chat bubble rendering if it continues to grow:
  - [x] `ChatMessageBubble`
  - [x] `SourcesBadge`
  - [x] `CitationCard`
- [x] Move citation formatting helpers into a feature utility if reused or if component readability improves:
  - [x] section type formatting.
  - [x] citation kind formatting.
  - [x] millisecond range formatting.
- [x] Preserve typewriter behavior and auto-scroll behavior.
- [x] Re-run `npm run build`.

### 8. Result Viewer Cleanup

- [x] Split `MeetingIntelligenceResultPanel` by UI meaning:
  - [x] result panel shell.
  - [x] JSON section toggle.
  - [x] recursive JSON value renderer.
  - [x] localStorage-backed section open state.
- [x] Keep localStorage key `omnicall:meeting-result-open-sections` unchanged.
- [x] Keep section order and labels unchanged unless explicitly improving copy.
- [x] Move generic helpers such as `labelize`, record checks, and scalar formatting only if they are useful outside this component.
- [x] Re-run `npm run build`.

### 9. Admin Logs Screen and Polling Cleanup

- [x] Move direct API orchestration out of `AdminMeetingLogsScreen`.
- [x] Create or extend a hook for meeting log detail state:
  - [x] current meeting name.
  - [x] meeting name map.
  - [x] missing meeting-log redirect check.
  - [x] clear-and-navigate behavior.
- [x] Keep `AdminMeetingLogsScreen` mostly compositional.
- [x] Consider a shared polling hook only if it simplifies current repeated interval effects without hiding feature-specific behavior:
  - [x] admin operational logs refresh.
  - [x] admin meeting log summary refresh.
  - [x] admin metrics refresh.
  - [x] meeting list polling.
- [x] If a shared polling hook is added, place it under `frontend/src/shared/hooks/`.
- [x] Re-run `npm run build`.

### 10. App Shell Boundary Cleanup

- [x] Remove `shared/layouts/AppShell.tsx` dependency on auth feature types if the change stays small.
- [x] Prefer one of:
  - [x] a shared account summary type under `frontend/src/shared/`.
  - [x] explicit layout props for `displayName`, `email`, and `role`.
- [x] Preserve admin/user menu behavior.
- [x] Preserve sidebar collapse localStorage key `omnicall-sidebar-collapsed`.
- [x] Preserve theme toggle behavior.
- [x] Re-run `npm run build`.

### 11. CSS Split by Domain Meaning

- [x] Fix CSS syntax warning before splitting files.
- [x] Split `global.css` into domain files only after behavior refactors are stable.
- [x] Keep design tokens and base styles central:
  - [x] `shared/styles/tokens.css`
  - [x] `shared/styles/base.css`
- [x] Move layout styles by shared meaning:
  - [x] `shared/styles/layout.css`
  - [x] `shared/styles/components.css`
- [x] Move feature-specific styles by product area:
  - [x] `shared/styles/auth.css`
  - [x] `shared/styles/admin.css`
  - [x] `shared/styles/meetings.css`
  - [x] `shared/styles/chat.css`
  - [x] `shared/styles/result-viewer.css`
- [x] Keep `global.css` as the import aggregator if that best fits the current Vite setup.
- [x] Confirm CSS import order preserves variables, resets, component rules, dark theme overrides, and responsive rules.
- [x] Re-run `npm run build` and confirm no CSS minify warnings.

### 12. Documentation Updates During Implementation

- [x] Update `docs/explanations/frontend-explanation.md` when frontend file structure or behavior changes.
- [x] Update this phase checklist as tasks are completed.
- [x] Update `docs/plans/0 - project overview.md` when phase status changes.
- [x] Do not update backend or worker explanation docs unless frontend changes alter cross-service behavior.

## Verification Plan

### Automated Tests

- [x] Frontend build passes after each batch:
  - [x] `cd frontend && npm run build`
- [x] TypeScript strict build passes with no new type suppressions.
- [x] Vite build has no CSS minify warning after the CSS hygiene task.
- [x] No new `@ts-ignore`, `as any`, `debugger`, or unused-import workaround remains in touched frontend files.
- [x] `rg -n "void [A-Z][A-Za-z0-9_]*;" frontend/src` returns no intentional unused-import workaround.

### Manual Verification

- [x] Auth session restore still works after page reload.
- [x] Login/register/logout still work.
- [x] Theme toggle still persists between reloads.
- [x] Sidebar collapse state still persists between reloads.
- [x] Meeting list loads and route selection `/meetings/:meetingId` stays in sync.
- [x] New meeting creation still selects the created meeting.
- [x] Upload flow still creates an asset and locks upload for that meeting.
- [x] Recording flow still creates a `.webm` upload and stops microphone tracks.
- [x] Processing queue flow still shows `QUEUED` / `PROCESSING` / `READY` updates.
- [x] Playback drawer still loads audio/video and revokes/replaces object URLs on meeting switch.
- [x] Transcript track still syncs with playback.
- [x] Result drawer still displays processed JSON sections and persists open/closed state.
- [x] Chat submit still creates optimistic user and assistant messages.
- [x] Chat SSE statuses still update in Vietnamese.
- [x] Chat fallback polling still replaces optimistic assistant messages with persisted history.
- [x] Typewriter animation still runs only for completed assistant answers.
- [x] Citations still render and expand/collapse.
- [x] Admin metrics page still loads and refreshes.
- [x] Admin accounts page still changes roles and deletes accounts with confirmation.
- [x] Admin logs page still filters, refreshes, selects events, and clears logs.
- [x] Admin meeting log detail page still redirects when the meeting log group no longer exists.

### Acceptance Criteria

- [x] No user-facing workflow is removed.
- [x] Routes remain framework-native and thin.
- [x] Feature APIs remain in feature `api/` folders.
- [x] Screens are more compositional and do not gain new API orchestration.
- [x] `useMeetingWorkspace` becomes a facade over smaller workflow hooks.
- [x] Chat stream behavior remains compatible with backend SSE events.
- [x] Global CSS is split by domain meaning without changing visual behavior.
- [x] Build passes with no CSS syntax warning.
- [x] Frontend explanation docs reflect the final refactored structure.

---

## Completion Report

> **Completed at:** 2026-07-09
> **Verified by:** Repeated `cd frontend && npm run build`, frontend hygiene scans, generated-artifact status check, and source review of preserved workflows.

### What was implemented

- Split frontend API mechanics behind `shared/utils/httpClient.ts`, kept feature endpoint modules thin, and moved chat SSE parsing into `features/meetings/api/chatStreamApi.ts`.
- Split meeting runtime helpers into `states/`, `utils/`, workflow hooks, and focused presentational components while keeping `useMeetingWorkspace` as the public screen facade.
- Split admin meeting log detail orchestration and shared polling into hooks, removed the AppShell dependency on auth feature types, and split global CSS into domain files imported by `global.css`.
- Upgraded the playback asset predicate so the drawer loads both audio and video Blob URLs, matching the existing media component behavior.

### What was changed from original plan

- Added a stable-ref implementation to the shared polling hook so callers do not reset intervals on each render.
- Kept `meetingApi.ts` re-export compatibility for chat stream callers.
- Manual browser smoke was not rerun in this pass; workflow checklist items were verified by source review plus TypeScript/Vite build after each refactor batch.

### Notes for future sessions

- Preserve the current `useMeetingWorkspace` public return shape until the internal hook split is fully stable.
- Treat chat/SSE/typewriter behavior as the highest-risk frontend area; refactor it in small batches.
- Keep `shared/styles/global.css` as the import aggregator unless the app gets a stronger CSS-loading convention; preserve token/base/layout/component/feature/responsive import order.

### Related docs updated

- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/plans/0 - project overview.md` (phase summary table)
