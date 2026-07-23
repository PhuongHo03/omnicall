# Frontend Explanation

> **Phase 47 authority:** chat diagnostics use only `pipelineTrace v1`. The former Agent Flow/Trace/Full Raw types, parsers, state, components, and SSE events have been removed.

## Pipeline Trace Viewer

`meetingDtos.ts` accepts the bounded backend trace stages `request_gate`, `query_interpretation`, `retrieval`, `evidence_validation`, `synthesis`, `answer_verification`, `output_policy`, and `persistence`. `PipelineTraceViewer` renders status, duration, effective provider/model, and bounded redacted details. `ChatMessageBubble` keeps citations and evidence-state badges beside the trace. The browser never receives full prompts, hidden reasoning, arbitrary tool payloads, answer-cache metadata, or Agent Memory state.

The chat stream parser accepts lifecycle/status/token/done/control/error/connected events only. Unknown former agent events are rejected at the DTO boundary; history/polling remains authoritative after reconnect.

## Structure

```text
frontend/
├── Dockerfile
├── index.html
├── package-lock.json
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
└── src/
    ├── main.tsx
    ├── routes/
    │   └── AppRoutes.tsx
    ├── shared/
    │   ├── components/
    │   │   ├── ConfirmDialog.tsx
    │   │   ├── Drawer.tsx
    │   │   ├── EmptyState.tsx
    │   │   ├── IconButton.tsx
    │   │   ├── IconOnlyButton.tsx
    │   │   ├── PageHeader.tsx
    │   │   └── ToastViewport.tsx
    │   ├── hooks/
    │   │   ├── useDebounceCallback.ts
    │   │   ├── usePollingEffect.ts
    │   │   └── useTheme.ts
    │   ├── layouts/
    │   │   ├── AppShell.tsx
    │   │   ├── SidebarContext.tsx
    │   │   └── ToastContext.tsx
    │   ├── styles/
    │   │   ├── global.css
    │   │   ├── tokens.css
    │   │   ├── base.css
    │   │   ├── layout.css
    │   │   ├── components.css
    │   │   ├── auth.css
    │   │   ├── admin.css
    │   │   ├── meetings.css
    │   │   ├── result-viewer.css
    │   │   ├── chat.css
    │   │   └── responsive.css
    │   ├── types/
    │   │   └── account.ts
    │   └── utils/
    │       ├── browserDownload.ts
    │       ├── httpClient.ts
    │       ├── id.ts
    │       └── retryWithBackoff.ts
    └── features/
        ├── admin/
        │   ├── api/
        │   │   └── adminApi.ts
        │   ├── components/
        │   │   ├── AdminAccountsTable.tsx
        │   │   ├── AdminLogDetails.tsx
        │   │   ├── AdminLogStream.tsx
        │   │   ├── adminLogProvenance.ts
        │   │   ├── AdminLogToolbar.tsx
        │   │   ├── AdminMetricsGroup.tsx
        │   │   ├── AdminSummaryCards.tsx
        │   │   └── AdminTargetsTable.tsx
        │   ├── dtos/
        │   │   └── adminDtos.ts
        │   ├── hooks/
        │   │   ├── useAdminAccounts.ts
        │   │   ├── useAdminLogs.ts
        │   │   ├── useAdminMeetingLogDetail.ts
        │   │   ├── useAdminMeetingLogs.ts
        │   │   └── useAdminMetrics.ts
        │   ├── screens/
        │   │   ├── AdminAccountsScreen.tsx
        │   │   ├── AdminMeetingLogsScreen.tsx
        │   │   ├── AdminLogsScreen.tsx
        │   │   └── AdminMetricsScreen.tsx
        │   └── types/
        │       └── adminTypes.ts
        ├── auth/
        │   ├── api/
        │   │   └── authApi.ts
        │   ├── dtos/
        │   │   └── authDtos.ts
        │   ├── hooks/
        │   │   └── useAuthSession.ts
        │   ├── screens/
        │   │   └── AuthScreen.tsx
        │   └── types/
        │       └── authTypes.ts
        └── meetings/
            ├── api/
            │   ├── chatStreamApi.ts
            │   ├── meetingApi.ts
            │   └── recordingStorage.ts
            ├── dtos/
            │   ├── chatStreamDtos.ts
            │   └── meetingDtos.ts
            ├── hooks/
            │   ├── useChatFeedback.ts
            │   ├── useMeetingAssetPlayback.ts
            │   ├── useMeetingChatWatch.ts
            │   ├── useMeetingRecording.ts
            │   ├── useMeetingSelection.ts
            │   ├── useMeetingStatusSync.ts
            │   ├── useMeetingWorkspace.ts
            │   └── useResultSectionState.ts
            ├── screens/
            │   └── MeetingsScreen.tsx
            ├── states/
            │   ├── chatFlowState.ts
            │   ├── chatState.ts
            │   └── meetingState.ts
            ├── types/
            │   └── meetingTypes.ts
            ├── utils/
            │   ├── chatTrace.ts
            │   ├── citationFormatters.ts
            │   ├── jsonDisplay.ts
            │   ├── markdownParser.ts
            │   ├── meetingFormatters.ts
            │   └── meetingTranscript.ts
            └── components/
                ├── AssetMetadataBar.tsx
                ├── AssetPlaybackPanel.tsx
                ├── ChatFlowBadge.tsx
                ├── ChatFlowTrace.tsx
                ├── ChatMessageBubble.tsx
                ├── JsonSection.tsx
                ├── JsonValue.tsx
                ├── MeetingActionPanel.tsx
                ├── MeetingChatPanel.tsx
                ├── MeetingIntelligenceResultPanel.tsx
                ├── MeetingList.tsx
                ├── MeetingRecordingStatus.tsx
                ├── MeetingProgressBar.tsx
                ├── PlaybackDrawer.tsx
                ├── PlayerControls.tsx
                ├── ResultDrawer.tsx
                ├── TranscriptTrack.tsx
                ├── WaveformDisplay.tsx
                └── StatusPill.tsx
```

The frontend follows the feature-based layered structure:

```text
URL -> route -> feature screen -> feature hook -> DTO/API -> backend
```

Routes are thin. The `auth`, `meetings`, and `admin` features own their API calls, response mapping, orchestration hooks, screen composition, feature-only components, and feature types. Cross-feature UI, layouts, global styles, utilities, and shared assets belong under `src/shared/` instead of root-level `src/components`, `src/layouts`, or `src/styles`.

## Runtime

The frontend is a Vite React TypeScript app using React Router for browser URL routing. In Compose, it runs as an internal-only service on port `5173`. The Docker image installs dependencies with `npm ci` from `package-lock.json`.

Traffic path:

```text
browser -> NGINX / -> frontend:5173
browser -> NGINX /api/ -> backend:8000
```

The frontend service is not host-published. The public local URL remains:

```text
http://127.0.0.1:8080
```

Implemented frontend routes:

| Route | Screen | Access |
|---|---|---|
| `/auth` | `AuthScreen` with Login/Register tabs | Guest; authenticated accounts redirect to `/meetings` |
| `/meetings` | Default meeting workspace with no meeting selected | Authenticated `User` and `Admin` |
| `/meetings/:meetingId` | `MeetingsScreen` with a selected meeting | Authenticated `User` and `Admin` |
| `/admin/metrics` | `AdminMetricsScreen` | `Admin` only |
| `/admin/accounts` | `AdminAccountsScreen` | `Admin` only |
| `/admin/logs` | `AdminLogsScreen` | `Admin` only |

`/` redirects to `/meetings` after authentication and to `/auth` for guests. `/admin` redirects to `/admin/metrics`, which is the default admin portal page. Unknown URLs redirect to `/auth` or `/meetings`. Non-admin accounts attempting `/admin/*` are redirected to `/meetings`.

## Meeting Workspace UI

`AppRoutes` gates the application behind backend-owned authentication. If no valid bearer token/account is available, protected routes redirect to `/auth`. After login/register, the frontend stores the local session token in `localStorage`, calls `GET /api/me`, and redirects into the authenticated route tree.

`AuthScreen` starts empty and keeps Login and Register as two tabs/forms within the same `/auth` route because they are two modes of the same account-access screen. Registration validates email format with a simple `name@example.com` pattern, keeps the display name free-form, accepts any non-empty password length, and requires a matching confirm-password field. Registration no longer exposes a role selector; new public accounts are created as `User` by the backend. Backend validation remains authoritative; `authApi` parses FastAPI validation errors and safe backend error payloads into user-visible messages instead of showing a generic request failure.

`MeetingsScreen` composes the implemented meeting workspace. Account identity is no longer repeated inside the meeting content area, leaving the center column entirely for meeting actions, results, and chat:

| Area | Component | Purpose |
|---|---|---|
| Meeting list and creation | `MeetingList` | Lives in the shared sidebar slot, lists meetings, creates a new analysis, and selects the current meeting |
| Meeting actions | `MeetingActionPanel` | Shows the selected meeting, inline rename control, one-file upload/record controls, process/retry button, playback/result actions, refresh actions, and delete action |
| Playback drawer | `PlaybackDrawer`, `AssetPlaybackPanel`, `PlayerControls`, `TranscriptTrack`, `WaveformDisplay` | Loads the selected meeting asset into a temporary browser Blob URL, provides playback controls, transcript navigation, and download |
| Processed JSON result | `ResultDrawer`, `MeetingIntelligenceResultPanel`, `JsonSection`, `JsonValue` | Renders the generalized `meeting-intelligence-result.v2` as readable collapsible sections, including generic `knowledge.records` and `evidence.items` |
| Meeting chat | `MeetingChatPanel`, `ChatMessageBubble` | Asks questions against a ready meeting, renders immediate user bubbles, pending assistant state, streamed answer text, saved evidence state, citations, and source expansion |
| Status display | `StatusPill` | Displays meeting and job state |

Meeting selection is URL-backed. `/meetings` is the authenticated landing page and intentionally keeps no meeting selected. Opening `/meetings/:meetingId` selects that meeting after the authorized meeting list loads. Selecting or creating a meeting updates the URL, deleting the selected meeting returns to `/meetings`, and clicking the navbar Meetings button always returns to `/meetings`. The Meetings panel creates a backend-owned meeting shell immediately; the backend names the shell with its generated meeting ID until the user renames it from the selected meeting header. This supports refresh, browser back/forward navigation, bookmarks, and direct links without moving business authorization into the frontend.

## Admin Portal UI

The app shell shows one `Admin Portal` dropdown on the right only when the authenticated account role is exactly `Admin`. Beside logout, the account trigger shows the account display name instead of the role label and uses a role-specific icon: a shield for `Admin` and a user icon for `User`. Hovering it or focusing it with the keyboard reveals the authenticated display name, email, and role. The dropdown links to three independent routes and data lifecycles:

```text
Metrics link -> /admin/metrics -> AdminMetricsScreen -> useAdminMetrics -> GET /api/admin/metrics
Accounts link -> /admin/accounts -> AdminAccountsScreen -> useAdminAccounts -> account admin APIs
Logs link -> /admin/logs -> AdminLogsScreen -> useAdminLogs -> operational log APIs
```

The logs page has separate Processing Logs and RAG Chat Logs tabs. Each row shows the event level, time, stage, session, file or bounded question preview, typed executor provenance, duration, status, and error type when present. Selecting a linked RAG event shows the durable Question and turn/user message IDs returned by the admin API. The Answer and assistant message ID appear only on the terminal `answer` event, never retroactively on `received`, `queued`, guardrail, resolver, Agent, or tool events after the turn completes. Older or pre-linkage events gracefully remain preview-only. The Event metadata JSON excludes duplicated full Question/Answer bodies and keeps only traceback fields.

Labels follow the executor type and show only runtime provenance: LLM Provider/Model, Embedding Provider/Model, Vector Store/Collection, Rule Engine/Rule, ASR, diarization, worker, cache store, or implementation/component. Configured/default provider values are intentionally omitted from row badges, the details grid, and displayed Event metadata because they did not execute the event. A pipeline-only `Agent started` event therefore has no Provider/Model. Query resolution shows its effective interpreter provider; terminal answer events show the actual answer producer. A served cache hit puts the cached answer's origin under `Answer Provider/Model` and identifies Redis separately as `Cache Store`. In particular, `local-direct-intent` is displayed as `Implementation` with component `closed-direct-intent-router`, never as Provider/Model. Fallback use remains explicit. Controls provide a left-icon search input, `All`/`Info`/`Error`, a compact Tail selector with sizes of 100/300/1000, manual refresh, a button-style two-second Live toggle, and confirmed clear. The browser calls only authenticated backend APIs and never connects directly to Redis or PostgreSQL.

The metrics page auto-refreshes every 30 seconds and renders:

| Area | Source |
|---|---|
| Summary cards | Backend-normalized health, target counts, and Redis cache state |
| Target table | Prometheus target health returned by the backend |
| Metric groups | Combined `Meeting Operations`, `Backend`, `Containers`, and combined `Infrastructure Services` metrics returned by the backend |

Backend request-rate rows combine the Prometheus `method`, `path`, and `status` labels, for example `GET · /admin/metrics · 200`, so each rate can be attributed to a specific endpoint and response status.
Backend p95-latency rows combine `method` and `path`, for example `GET · /admin/metrics`, while the displayed duration represents the 95th-percentile latency over the five-minute query window.
Meeting, chat, and processing-job metrics share one `Meeting Operations` presentation section while retaining their separate backend categories and Prometheus meanings; this section is pinned before backend metrics in the dashboard order.
Container CPU and memory rows use the Docker Compose service label, such as `backend`, `worker`, or `milvus`, rather than the shared Prometheus scrape-job label `docker`.
Database, cache, queue, storage, vector, and gateway cards share one `Infrastructure Services` presentation section laid out as two columns on desktop. Related cards are pinned together by row: PostgreSQL connection and size cards, Redis cards, RabbitMQ cards, MinIO cards, vector-store cards, and NGINX starting its own final row when no paired card remains.
Infrastructure singleton metrics use semantic row labels such as `used memory`, `total consumers`, `used by objects`, and `active connections` instead of repeating the source service name.
Metric cards render every series returned by the backend for that metric rather than truncating rows in the frontend.

The browser never calls Prometheus directly and does not contain PromQL. Admin authorization, Prometheus querying, normalization, and Redis caching remain backend responsibilities. Hiding the dashboard button for non-admin users is UX only; backend still returns `403 admin_access_required`.

Admin access is guarded twice in the frontend: non-admin accounts do not receive the dropdown, and `AdminRoute` redirects direct `/admin/*` navigation to `/meetings`. Backend role checks remain the authoritative security boundary.

The accounts page renders `AdminAccountsTable`, backed by `GET /api/admin/accounts`, `PATCH /api/admin/accounts/{userId}/role`, and `DELETE /api/admin/accounts/{userId}`. Admins can change another account's role with a dropdown or delete another account. The current admin's dropdown and delete action are disabled, and backend still enforces `409 cannot_change_own_role` or `409 cannot_delete_own_account` if a direct request tries to modify the caller's account.

The recording entry point and manual file picker converge on one explicit `uploadFileToMeeting(meetingId, file)` orchestration and the same backend asset endpoint. A recording session captures its owner and meeting IDs before requesting microphone permission, negotiates a backend-supported WebM/Opus, WebM, or MP4 audio MIME type, and calls `MediaRecorder.start(1000)` so ordered chunks are available every second. Recording is not live transcription.

`recordingStorage.ts` persists session metadata and ordered chunk `ArrayBuffer` values in browser IndexedDB under the authenticated owner and meeting identity. Stop flushes the last chunk, rebuilds a `File`, repairs missing WebM duration metadata using the measured recording duration, and uploads it to the captured meeting rather than the mutable UI selection. Successful authoritative upload or explicit Discard removes local data. Permission, storage, finalization, and upload failures remain visible; a saved recording can be retried, downloaded, or discarded. Reload recovery is best effort: a session interrupted during active recording is marked partial and can lose the last chunk that the browser had not emitted. IndexedDB is local to that browser and does not provide cross-device durability.

`MeetingActionPanel` follows the one-analysis-per-meeting rule. Upload and recording are shown only while the selected meeting is `DRAFT` and has no asset. During permission, recording, finalization, upload, failure recovery, or partial recovery, Upload remains visible but disabled; only the owner meeting may show Stop. Meeting creation/selection, rename, delete, process, refresh, and competing upload handlers are locked in both presentation and orchestration layers. URL-backed selection restores the owner meeting when history requests another meeting, and full-page unload receives a browser warning. Once a file is uploaded, intake controls are hidden and the meeting is locked to that asset whether processing later succeeds or fails. Backend validation remains authoritative and returns `409 Conflict` for stale or direct requests.

Meeting processing failures are localized at the feature boundary. The meeting DTO retains the backend's safe English `failureReason` for diagnostics but `MeetingsScreen` never renders it directly; it maps the stable `failureCode` to Vietnamese presentation text. `NO_RECOGNIZABLE_SPEECH` explains that no clear speech was detected while keeping playback/download available, and unknown or generic failures use a non-technical Vietnamese fallback. Admin operational-log screens continue to render the backend's English technical events unchanged.

The process action treats both `QUEUED` and `PROCESSING` meetings as actively processing: the button displays `Processing` and is disabled, while rename and delete remain locked until processing completes. The workspace reuses `EmptyState` for meeting lifecycle feedback: draft meetings ask for an audio file, uploaded meetings prompt the user to press `Process`, upload requests show a determinate `MeetingProgressBar`, queued/processing meetings show an indeterminate progress bar, and failed meetings show a retry message. Ready meetings continue to render the chat panel.

The central workspace no longer uses operation/chat tabs. It is a chatbot-style flow: meeting controls stay at the top, playback and processed-result details open in drawers, and the meeting chat composer/thread fills the selected meeting workspace after the meeting is `READY`. The processed JSON panel remembers open/closed section state locally in the browser so switching meetings does not force sections back open after the user closes them. Phase 22 updated the preferred section order and labels for the RAG-first schema: evidence, speakers, facts, events, relationships, topics, summaries, actions, decisions, risks, questions, and extraction are first-class sections. The shared app sidebar behaves like a modern chat history rail for selecting or creating analyses.

The current visual system uses a neutral operational surface, white raised panels, and multiple restrained accents: green for primary actions/ready states, indigo for queued states, amber for in-progress or partial states, and coral for destructive/error states. Cards and controls keep the existing 8px radius limit while using slightly stronger spacing, panel shadows, and focus states for a more modern workspace feel.

Global CSS is loaded from `shared/styles/global.css`, which is now only an import aggregator. Domain files keep the cascade readable: `tokens.css` defines the shared design contract for font families, text sizes, line heights, radius values, core colors, semantic alpha colors, overlays, shadows, focus rings, and dark-theme overrides. `base.css` handles reset/base elements and generic controls, `layout.css` owns the app shell/sidebar, `components.css` owns shared UI components and dark shared overrides, `auth.css`, `admin.css`, `meetings.css`, `result-viewer.css`, and `chat.css` own feature/product-area styles, and `responsive.css` keeps viewport overrides together.

Phase 20 tightened visual consistency by moving avoidable one-off color, radius, shadow, line-height, overlay, and mono-font values into `tokens.css`. Feature CSS now uses those variables for reusable primitives; React keeps inline styles only where the value is dynamic runtime state, such as playback and transcript progress widths.

## API And DTO Boundaries

`authApi.ts`, `meetingApi.ts`, and `adminApi.ts` are intentionally thin. They keep feature-specific endpoint functions in each feature `api/` folder and delegate shared request mechanics to `frontend/src/shared/utils/httpClient.ts`, including API prefix handling, bearer headers, JSON headers, JSON parsing, blob parsing, and normalized backend error extraction.

`meetingDtos.ts` maps backend snake_case responses into frontend camelCase types and performs basic runtime shape checks.

Meeting chat calls are handled through the same feature boundary:

```text
MeetingChatPanel -> useMeetingWorkspace -> meetingApi/chatStreamApi -> /api/meetings/{meetingId}/chat
```

Chat request building and response/history mapping live in `meetingDtos.ts`. Each new chat request includes the browser's `navigator.language`; the backend uses it as the output locale and falls back to its deployment default for clients that omit it. REST chat calls remain in `meetingApi.ts`; `chatStreamApi.ts` owns the connection and `chatStreamDtos.ts` runtime-validates lifecycle/status/token/done/control/error/connected events. The frontend keeps only lightweight UI state: current question text, temporary optimistic messages, the bounded `pipelineTrace v1`, and backend-returned messages. It does not create, store, or send a chat-session ID. Unknown or malformed events are dropped, and a failed stream recovers through history polling.

The accepted chat response supplies a durable `turnId`. `useMeetingChatWatch` passes it to the SSE URL and ignores nonmatching progress/terminal events, then replaces the optimistic assistant message immediately from the terminal persisted payload. The backend replays the most recent durable stage on connection, so the optimistic `queued` label is replaced even when the initial Pub/Sub event occurred before the stream opened. A terminal SSE `error` is rendered immediately; history polling remains a fallback for network interruption. While a turn is pending, each SSE pipeline-stage update builds a temporary `pipelineTrace` with completed prior stages and one `in_progress` current stage; the persisted trace with real durations/details replaces it at completion. The owner-facing viewer is labeled `Steps (n)` and uses the same message-card scroll behavior as the Citations badge when opened.

### Resilience Hooks and States

- `useDebounceCallback` hook in `frontend/src/shared/hooks/` provides generic debouncing with `.cancel()` support and unmount cleanup.
- `usePollingEffect` hook in `frontend/src/shared/hooks/` centralizes interval setup for admin logs, admin metrics, admin meeting-log summaries, and meeting status polling while keeping each feature's fetch behavior local.
- `useMeetingWorkspace` remains the public facade for `MeetingsScreen`, but selection, status/list polling, chat watch, recording, playback Blob URL lifecycle, transcript extraction, and browser download behavior are split into smaller feature hooks/utilities.
- Duplicate request guards prevent the same action from running concurrently (e.g. clicking Refresh 10 times only sends 1 request).
- `useAuthSession.refreshAccount()` distinguishes transient network errors from real auth failures: network errors keep the session token; only server 401 removes it.
- Meeting API functions (`listMeetings`, `getMeeting`, etc.) accept an optional `AbortSignal` for request cancellation.

Assistant messages display the backend evidence state and citation-level evidence. `ChatFlowBadge` renders a collapsible `Flow (n)` badge beside `Citations (n)` with three views. `Summary` shows plan intent/answer shape, exact code-level tool names, result counts, per-iteration sufficiency, replans/cache state, and the final evidence/citation result. `Trace` uses the pure `chatTrace.ts` projection to retain only answer-affecting interpretation/plan fields, LLM action and decision code, exact tool calls/parameters, tool outcome counts, at most 20 unique evidence previews with citation health, evidence verification, synthesis claims, repair evidence-ref diff, claim/goal verification, final state transition, and automatically derived failure findings. `Full Raw` keeps the owner-visible JSON captured from query interpretation, executable plan, each LLM decision, exact tool parameters/results/errors, evidence verification, synthesis/repair, claim verification, and goal coverage. Full Raw may contain meeting text, contact data, queries, and provider/tool details; hidden reasoning tokens and prompts remain unavailable.

Transcript playback extracts entries from `transcript.segments` and now prefers `speakerLabel` while keeping `speaker` as a fallback for renderer compatibility. The frontend does not infer participant counts, events, facts, or relationships; those remain backend-owned intelligence records.

For selected meetings, the hook loads `GET /api/meetings/{meetingId}/processing-status` to retrieve the latest job and latest asset, then loads `GET /api/meetings/{meetingId}/intelligence-result` when the meeting is `READY`. Playable asset loading has explicit idle/loading/ready/error state. The authenticated content request is aborted when stale, its temporary Blob URL is revoked when meeting or asset identity changes, drawers close on selection changes, and the player stays disabled until media metadata or decoded Web Audio duration is available. Decoded duration keeps total time, waveform progress, and seeking usable for older MediaRecorder WebM assets whose container reports no finite duration. A missing or mismatched asset renders a safe empty/error state instead of asserting a non-null value. While a meeting is `QUEUED` or `PROCESSING`, the hook polls processing status every 3 seconds. The frontend does not parse or recompute intelligence sections; it renders the JSON returned by the backend.

Meeting deletion is exposed in `MeetingActionPanel` for authenticated `User` and `Admin` accounts. It asks for in-app confirmation before calling owner-scoped `DELETE /api/meetings/{meetingId}` through the meeting API wrapper with the current bearer token, then clears the selected meeting and reloads meeting state. The backend remains authoritative and returns `404` if a direct request targets another account's meeting.

Destructive UI actions ask for confirmation before sending requests: meeting-session delete in `MeetingActionPanel` and account delete in `AdminAccountsTable`. These confirmations use the shared in-app `ConfirmDialog` component instead of browser-native `window.confirm`, so the browser cannot suppress later confirmations with a "don't ask again" option. These confirmations are UX guardrails only; backend authorization and reference checks remain authoritative.

The frontend does not enforce business rules. Backend remains authoritative for authorization, upload validation, state transitions, idempotency, and processing eligibility.

## Verification

Verified commands:

```bash
npm run build
docker compose up -d --build frontend nginx
docker compose exec -T frontend npm run build
docker compose build frontend
curl -i http://127.0.0.1:8080/
```

Playwright verification:

| Check | Result |
|---|---|
| Desktop screenshot at `1440x900` | Passed |
| Mobile screenshot at `390x844` | Passed |
| UI smoke: create meeting, upload `.wav`, process, see `QUEUED` | Passed |
| Phase 5 chat UI TypeScript/Vite build | Passed |
| Status-aware upload/record/process control build | Passed |
| Gateway frontend response after chat UI wiring | `200` |
| Chatbot-style left-sidebar UI TypeScript/Vite build | Passed |
| Gateway frontend response after left-sidebar UI rebuild | `200` |
| Audio playback panel TypeScript/Vite build | Passed |
| Gateway asset content smoke for uploaded MP3 | `200`, `audio/mpeg`, expected byte count |
| Phase 6 admin dashboard TypeScript/Vite build | Passed |
| Phase 7 auth/account/file/admin UI TypeScript/Vite build | Passed |
| Gateway smoke for register/login/me/file library/admin delete | Passed |
| Auth form validation/error-message update TypeScript/Vite build | Passed |
| Optimistic chat/typewriter UI TypeScript/Vite build | Passed |
| Admin account role-management TypeScript/Vite build | Passed |
| Gateway smoke for default User registration and admin role management | Passed |
| Account delete + destructive confirmation TypeScript/Vite build | Passed |
| Backend full suite after account deletion hardening | `75` tests passed |
| Shared folder refactor and in-app confirm dialog TypeScript/Vite build | Passed |
| React Router route split and admin metrics/accounts separation build | Passed |
| Navbar account hover dropdown and meeting account-banner removal build | Passed |
| Phase 8 Admin logs TypeScript/Vite build and NGINX route smoke | Passed |
| Phase 19 frontend refactor safety cleanup TypeScript/Vite build | Passed |
| Phase 19 CSS split Vite build with no CSS minify warning | Passed |
| Phase 19 no unused-import workaround scan | Passed |
| Phase 20 frontend design token cleanup TypeScript/Vite build | Passed |
| Phase 20 hard-coded style scan outside `tokens.css` | Passed |
| Phase 44 frontend Vitest suite | `25` tests passed across `9` files |
| Phase 44 TypeScript/Vite production build | Passed (`1,791` modules transformed) |
| Phase 45 recording/playback and localized failure Vitest suite | `38` tests passed across `15` files |
| Phase 45 TypeScript/Vite production build | Passed (`1,794` modules transformed) |
| Phase 45 WebM duration repair follow-up | `37` tests across `15` files; build passed with `1,823` modules; reported asset repaired from `Duration: N/A` to `1.333000s` |

Earlier phase screenshots were generated under ignored `tmp/screenshots/`.

Playwright screenshot re-verification was attempted on 2026-06-17, but the local Playwright package could not install Chromium because the current environment reports `ubuntu26.04-x64`, which Playwright did not support for that browser build. The verified fallback for the Phase 20 design-token cleanup pass is TypeScript/Vite build, static source review, and frontend style scans.

## Historical Agentic RAG Frontend (Removed In Phase 47)

### New SSE Events

The frontend now handles additional SSE events for the Agentic RAG agent loop:

| Event | Type | Description |
|-------|------|-------------|
| `agent_think` | `{ type, iteration }` | Shows agent iteration progress |
| `agent_plan` | `{ type, iteration, intent, answerShape }` | Shows sanitized retrieval intent/answer-shape status |
| `agent_search` | `{ type, iteration, tools, message }` | Shows tools being called |
| `observation` | `{ type, iteration, resultCount, successCount, failureCount }` | Shows sanitized retrieval counts |
| `agent_verify` | `{ type, iteration, sufficient }` | Shows evidence sufficiency |
| `agent_replan` | `{ type, iteration, replanCount }` | Shows bounded evidence replan |
| `agent_synthesize` | `{ type, iteration?, forced?, message? }` | Shows final-answer generation status |
| `fast_path` | `{ type, intent, message }` | Shows immediate response |
| `clarification` / `clarification_needed` | `{ type, message, assistantMessage? }` | Ends the turn with the persisted clarification bubble |
| `connected` | `{ type: "connected", status: "connected" }` | Initial stream handshake |

### Public chat metadata

`meetingDtos.ts` maps only the backend's user-visible metadata allowlist:

```typescript
type MeetingChatMessageMetadata = {
  evidenceState?: ChatEvidenceState;
  confidence?: number;
  cache?: { hit: boolean; mode?: "exact" | "semantic" };
  conversationContextTurns?: number;
  conversationContextUsed?: boolean;
  conversationContextTruncated?: boolean;
  dependencyMode?: "standalone" | "resolved" | "ambiguous";
  feedbackEligible?: boolean;
  clarificationNeeded?: boolean;
  agentIterations?: number;
  agentReplans?: number;
  agentToolNames?: string[];
  agentFlow?: {
    version: 1;
    steps: Array<{
      iteration: number;
      tools: string[];
      resultCount?: number;
      successCount?: number;
      failureCount?: number;
      sufficient?: boolean;
    }>;
  };
  agentRawFlow?: ChatAgentRawFlow;
  intent?: string;
  answerShape?: string;
};
```

Unknown metadata is discarded during runtime mapping. `agentFlow` remains a versioned summary capped at eight iterations. `agentRawFlow` is a separate versioned owner-visible contract whose nested values are runtime-validated as JSON while preserving provider field names and tool identifiers exactly. It contains raw returned payloads and tool execution data by explicit product choice, so it is not a redaction or security boundary. Legacy `agentThoughts`, prompts, memory IDs, token details, Redis keys, and hidden model reasoning remain outside browser state.

Agent SSE handling is defensive: every decoded object passes through a discriminated runtime parser before dispatch, and `useMeetingChatWatch` applies the tool allowlist again before writing progress metadata. `agent_search`, `observation`, and `agent_synthesize` events may arrive with only structured fields such as `tools`, `resultCount`, or `forced`, so the watcher derives a safe Vietnamese status message instead of assigning `undefined` into chat message content. Terminal events prefer their already-sanitized persisted `assistantMessage`; polling/history recovery remains authoritative after malformed or lost stream events. The markdown/typewriter renderer treats missing transient content as an empty string so one malformed event cannot crash the thread.

### UI Components

| Component | Feature |
|-----------|---------|
| `ChatMessageBubble` | Places the answer, evidence state, Flow/Citations badges, and feedback controls |
| `ChatFlowBadge` | Switches between Summary, filtered Trace, and Full Raw views |
| `ChatFlowTrace` | Renders traceback-focused stages, evidence citation health, repair diff, final downgrade, and failure findings |

### CSS Classes

| Class | Purpose |
|-------|---------|
| `.chat-message__insights` | Keeps Flow and Citations badges adjacent and responsive |
| `.flow__panel` / `.flow__row` | Collapsible execution timeline and individual stages |
| `.agent-tool-badge` | Individual tool badges |

## Typewriter Expansion (Phase 17)

The typewriter effect has been expanded to work for ALL assistant message evidence states, not just grounded/partial messages.

### Supported Evidence States

| Evidence State | Typewriter | Visual Style |
|----------------|------------|--------------|
| `grounded` | ✅ | Green border |
| `partial` | ✅ | Amber border |
| `not_enough_evidence` | ✅ | Amber border + background |
| `fast_path` | ✅ | Green border + background |
| `blocked` | ✅ | Muted border + faint background |
| `error` | ✅ | Red border + danger background |

### Implementation Changes

**MeetingChatPanel.tsx:**
- Removed `!isStreaming` restriction from typewriter activation
- Added evidence state CSS class to chat message container
- Typewriter now activates for all assistant messages (except `isTyping` state)

**useMeetingWorkspace.ts:**
- SSE `done`/`blocked` handler adds typewriter IDs for ALL new assistant messages
- Polling handler adds typewriter IDs for ALL new assistant messages
- No longer limited to only the last message

**global.css:**
- No CSS changes needed (existing evidence badge styles are sufficient)

### Typewriter Activation Logic

```typescript
// Before: Only for grounded/partial
enableTypewriter && !isTyping && !isStreaming && message.role === "assistant"

// After: For ALL assistant messages
enableTypewriter && !isTyping && message.role === "assistant"
```

### Evidence Badge Display

All evidence states display a badge with appropriate styling:
- `grounded`: Green badge
- `partial`: Amber badge
- `not_enough_evidence`: Amber badge
- `fast_path`: Green badge
- `blocked`: Muted badge
- `error`: Red badge

The meeting result panel renders `meeting-intelligence-result.v2` as generic JSON sections, including `knowledge.records` and `evidence.items`, without flattening subtype records into hardcoded top-level UI sections. A `KnowledgeRecord` carries canonical type, subtype, payload, evidence references, source references, and derivation metadata; playback remains available only through chat citations that contain transcript location data.

Meeting feedback follows the feature layers: `meetingApi.ts` sends the owner-scoped revisioned request, `meetingDtos.ts` validates/maps the response, `useChatFeedback` owns optimistic orchestration and rollback, `chatState.ts` owns eligibility/toggle transitions, and `ChatMessageBubble` renders the controls. Feedback is shown only for persisted terminal assistant answers whose backend metadata marks an eligible evidence state; local, pending, streaming, blocked, error, fast-path, and clarification messages do not expose the buttons.

Each message has an independent pending set. While its request is in flight both buttons are disabled and the group exposes `aria-busy`; `aria-pressed` reflects the selected rating. Clicking an unselected button sends `up` or `down`; clicking the selected button sends `neutral`. The UI applies an optimistic message-local state, accepts the server response as authoritative, and rolls back on error. The response DTO preserves backend lifecycle values such as `source_retained`, `promoted`, and `semantic_mapping_quarantined` instead of collapsing them to an unknown state. Request versions and meeting/token scope versions prevent a late mutation response from overwriting newer state. All chat-history replacement paths use a deterministic merge: a stale GET cannot overwrite pending feedback or a higher `feedbackRevision`, while a genuinely newer server revision wins. Chat history maps top-level `feedback_rating`/`feedback_revision`, so refresh preserves `up`/`down` and renders persisted neutral as no selected button.

Only one question may be active for a meeting. On backend `409 chat_busy`, the workspace restores the submitted text unless the user has already typed a newer draft, refreshes persisted history, continues watching the in-flight turn, and sends the backend-safe message to the global toast surface. Feedback rollback errors use the same surface. `ToastProvider` is mounted once around the authenticated App Shell, while `ToastViewport` renders a single fixed toast at the top center of the UI across meeting and admin routes. Success notices auto-dismiss after four seconds and errors remain until explicitly dismissed or replaced; both variants expose an accessible close control.

Meeting operations publish their terminal result directly to this shared surface, so create and delete notices survive meeting selection/route changes and stopping a recording remains visible while its upload starts. The meeting Refresh button performs one authoritative refresh path. It uses the meeting state returned by that request: a `READY` meeting whose result and chat history were rehydrated emits `Chat refreshed.`, while non-chat states emit `Status refreshed.`. It does not launch a second competing chat-history request. Synchronous and SSE/polling clarification results render only as persisted assistant chat bubbles inside the polite live chat thread; they do not duplicate the same conversational content in a toast.

Admin hooks do not announce initial loads, polling, or background refreshes. The explicit Refresh buttons on Metrics, Accounts, Logs, and Meeting Log Detail opt into a global success/error toast; existing non-refresh admin mutations keep their own feature-local state and do not publish to the shared toast surface.

*Document reflects project state during **Phase 47 Query Graph Discourse and Evidence Branch Architecture (In Progress)**. Frontend recording recovery remains owner/meeting-scoped, while admin operational logs render backend-owned typed executor provenance and PostgreSQL-hydrated chat traceback.*
