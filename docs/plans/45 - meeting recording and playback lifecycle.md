# Phase 45 - Meeting recording and playback lifecycle

## Status: In Progress

## Objectives

1. Route browser recordings and selected files through one meeting-owned upload pipeline.
2. Persist timed recording chunks in owner-scoped IndexedDB storage so interrupted recordings remain recoverable on the same browser.
3. Prevent meeting navigation and destructive/action races while recording, finalization, upload, or recovery is active.
4. Reset playback safely when the selected meeting or asset changes.
5. Reject low-confidence no-speech hallucinations while keeping Admin diagnostics in English and Meetings failure messages in Vietnamese.

## Prerequisites

- [x] One-asset-per-meeting backend validation and idempotent asset upload are implemented.
- [x] The frontend meetings feature already separates API access, orchestration hooks, states, types, screens, and components.

## Tasks

### Recording persistence and upload

- [x] Add the recording lifecycle phases and bind each session to owner and meeting IDs.
- [x] Emit `MediaRecorder` chunks every second, persist ordered `ArrayBuffer` chunks in IndexedDB, and negotiate a backend-supported MIME type.
- [x] Finalize Stop into a `File` and upload it through the same explicit `uploadFileToMeeting(meetingId, file)` path as manual files.
- [x] Recover owner-scoped interrupted sessions and expose Retry, Download, and Discard actions.
- [x] Delete local chunks only after authoritative upload success or explicit Discard; warn when browser persistence fails.

### Workspace safety and playback

- [x] Lock meeting selection, creation, rename, delete, process, refresh, and competing upload actions while recording work is unresolved.
- [x] Restore the recording-owner URL when browser history requests another meeting and warn before a full-page unload.
- [x] Close drawers on meeting changes, remove the unsafe playback asset assertion, and key player state by meeting/asset identity.
- [x] Add explicit playback loading/ready/error state, abort stale asset downloads, revoke Blob URLs, and disable controls until metadata is ready.
- [x] Repair missing WebM duration metadata before uploading new browser recordings and use decoded Web Audio duration as the playback/waveform fallback for existing assets.

### Transcript quality and localized failure UX

- [x] Reject ASR segments below the configured confidence threshold or above the configured no-speech probability threshold.
- [x] Classify an empty reliable ASR result as `NO_RECOGNIZABLE_SPEECH` while retaining English technical logs and safe backend reasons.
- [x] Return a stable meeting `failure_code` and map it to a user-facing Vietnamese message without rendering the English backend reason.

## Verification Plan

### Automated Tests

- [x] Run `cd frontend && npm test` - `38` tests passed across `15` files.
- [x] Cover IndexedDB owner isolation, chunk ordering/rebuild/delete, recording Stop/upload/retry ownership, WebM repair invocation, decoded-duration fallback, selection lock, playback error, and Blob URL cleanup.
- [x] Run `cd frontend && npm run build` - TypeScript and Vite production build passed (`1,823` modules transformed).
- [x] Probe the reported MinIO WebM asset: original `Duration: N/A`; repaired copy reports `1.333000s` while preserving Opus `48 kHz` stereo audio.
- [x] Run 17 targeted backend provider/pipeline unittests covering ASR quality filtering, no-speech classification, safe failure persistence, and existing voice processing behavior.

### Manual Verification

- [x] Record and Stop in the deployed browser UI; confirm the recording lifecycle and meeting lock behave correctly (user-verified 2026-07-16).
- [x] Refresh during a recording; confirm the owner meeting remains locked and Retry, Download, and Discard all work (user-verified 2026-07-16).
- [ ] Repeat Record/Stop/recovery in both Chromium and Firefox; confirm automatic `UPLOADED`, playback, and microphone release.
- [ ] Simulate upload failure and confirm meeting navigation remains locked until Retry succeeds or Discard is chosen.
- [ ] Record at least 5-10 seconds of clear speech, then confirm playback duration/waveform and successful ASR processing.

### Acceptance Criteria

- [x] Recording callbacks never infer the upload meeting from mutable UI selection.
- [x] Manual upload and recording share one upload orchestration and backend endpoint.
- [x] IndexedDB recordings cannot be restored across authenticated owner IDs.
- [x] Missing or changing playback assets cannot crash the drawer.
- [x] Refresh recovery keeps the owner meeting locked and exposes working Retry, Download, and Discard actions.
- [x] Low-confidence no-speech ASR output cannot become a transcript, and Meetings displays the classified failure in Vietnamese while Admin logs remain English.
- [ ] Chromium and Firefox manual scenarios pass.

---

## Completion Report

The deployed UI recording, Stop, refresh recovery, owner-meeting lock, and all three recovery actions were user-verified on 2026-07-16. Cross-browser and forced upload-failure verification remain pending.

### Related docs updated

- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
