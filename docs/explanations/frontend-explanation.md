# Frontend Explanation

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
    │   │   └── PageHeader.tsx
    │   ├── hooks/
    │   │   ├── useDebounceCallback.ts
    │   │   ├── usePollingEffect.ts
    │   │   └── useTheme.ts
    │   ├── layouts/
    │   │   ├── AppShell.tsx
    │   │   └── SidebarContext.tsx
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
            │   └── meetingApi.ts
            ├── dtos/
            │   └── meetingDtos.ts
            ├── hooks/
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
            │   ├── chatState.ts
            │   └── meetingState.ts
            ├── types/
            │   └── meetingTypes.ts
            ├── utils/
            │   ├── citationFormatters.ts
            │   ├── jsonDisplay.ts
            │   ├── markdownParser.ts
            │   ├── meetingFormatters.ts
            │   └── meetingTranscript.ts
            └── components/
                ├── AssetMetadataBar.tsx
                ├── AssetPlaybackPanel.tsx
                ├── ChatMessageBubble.tsx
                ├── JsonSection.tsx
                ├── JsonValue.tsx
                ├── MeetingActionPanel.tsx
                ├── MeetingChatPanel.tsx
                ├── MeetingIntelligenceResultPanel.tsx
                ├── MeetingList.tsx
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

The logs page has separate Processing Logs and RAG Chat Logs tabs. Each row already shows the event level, time, stage, session, file or question preview, provider/model, duration, status, and error type when present; selecting an event only opens deeper structured metadata. Controls provide a left-icon search input, `All`/`Info`/`Error`, a compact Tail selector with sizes of 100/300/1000, manual refresh, a button-style two-second Live toggle, and confirmed clear. The browser calls only the authenticated backend APIs and never connects directly to Redis.

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

The recording entry point uses `MediaRecorder` to produce a completed `audio/webm` file and uploads it through the same asset endpoint as normal file uploads. It is not live transcription.

`MeetingActionPanel` follows the one-analysis-per-meeting rule. Upload and recording are shown only while the selected meeting is `DRAFT` and has no asset. The file picker accepts audio and supported video files only, matching the backend voice-only meeting processing allowlist. Once a file is uploaded, the intake box is hidden and the meeting is locked to that asset whether processing later succeeds or fails. Processing remains available for an uploaded asset and retryable after a failed job. These controls are UI affordances only; backend state validation remains authoritative and returns `409 Conflict` for stale or direct requests that try to upload another file.

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

Chat request building and response/history mapping live in `meetingDtos.ts`. REST chat calls remain in `meetingApi.ts`, while SSE parsing and stream-event typing live in `chatStreamApi.ts`. The frontend keeps only lightweight UI state: current question text, temporary optimistic messages while an answer is pending, and the message list returned by the backend. It does not create, store, or send a chat-session ID. When a question is submitted, `useMeetingWorkspace` immediately adds the user bubble and a local assistant `Đang chờ xử lý...` bubble. `useMeetingChatWatch` consumes the legacy status/search/observation/synthesis events plus Phase 26 `agent_plan`, `agent_verify`, and `agent_replan` events. It renders sanitized Vietnamese status text and replaces local optimistic state with persisted chat history from `GET /api/meetings/{meetingId}/chat`. Unknown or missing optional event fields remain safe, and a failed stream recovers through history polling.

### Resilience Hooks and States

- `useDebounceCallback` hook in `frontend/src/shared/hooks/` provides generic debouncing with `.cancel()` support and unmount cleanup.
- `usePollingEffect` hook in `frontend/src/shared/hooks/` centralizes interval setup for admin logs, admin metrics, admin meeting-log summaries, and meeting status polling while keeping each feature's fetch behavior local.
- `useMeetingWorkspace` remains the public facade for `MeetingsScreen`, but selection, status/list polling, chat watch, recording, playback Blob URL lifecycle, transcript extraction, and browser download behavior are split into smaller feature hooks/utilities.
- Duplicate request guards prevent the same action from running concurrently (e.g. clicking Refresh 10 times only sends 1 request).
- `useAuthSession.refreshAccount()` distinguishes transient network errors from real auth failures: network errors keep the session token; only server 401 removes it.
- Meeting API functions (`listMeetings`, `getMeeting`, etc.) accept an optional `AbortSignal` for request cancellation.

Assistant messages display the backend evidence state and citation-level evidence. After streaming completes, unique verified citations are shown under a `Citations (n)` badge. Each citation displays its quote, processed JSON section pointer, source label, and transcript time range when available. Transcript citations expose a playback action that opens the playback drawer, seeks to `startMs`, and focuses the matching transcript segment when `segmentIds` are available. Structured sources such as facts, events, participants, relationships, topics, meeting metadata, quality warnings, and extraction warnings remain readable without a playback action when no transcript location exists. Legacy persisted citation records are normalized by the DTO mapper. Unsupported answers are shown as normal assistant messages with the backend `not_enough_evidence` state rather than optimistic certainty.

Transcript playback extracts entries from `transcript.segments` and now prefers `speakerLabel` while keeping `speaker` as a fallback for renderer compatibility. The frontend does not infer participant counts, events, facts, or relationships; those remain backend-owned intelligence records.

For selected meetings, the hook loads `GET /api/meetings/{meetingId}/processing-status` to retrieve the latest job and latest asset, then loads `GET /api/meetings/{meetingId}/intelligence-result` when the meeting is `READY`. When the latest asset is playable audio or video, the hook fetches `GET /api/meetings/{meetingId}/assets/{assetId}/content` with the bearer token, creates a temporary browser Blob URL, and revokes it when the selected meeting or asset changes. While a meeting is `QUEUED` or `PROCESSING`, the hook polls processing status every 3 seconds. The frontend does not parse or recompute intelligence sections; it renders the JSON returned by the backend.

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

Earlier phase screenshots were generated under ignored `tmp/screenshots/`.

Playwright screenshot re-verification was attempted on 2026-06-17, but the local Playwright package could not install Chromium because the current environment reports `ubuntu26.04-x64`, which Playwright did not support for that browser build. The verified fallback for the Phase 20 design-token cleanup pass is TypeScript/Vite build, static source review, and frontend style scans.

## Agentic RAG Frontend (Phase 26)

### New SSE Events

The frontend now handles additional SSE events for the Agentic RAG agent loop:

| Event | Type | Description |
|-------|------|-------------|
| `agent_think` | `{ type, iteration, message }` | Shows agent iteration progress |
| `agent_plan` | `{ type, iteration, intent, sections }` | Shows sanitized retrieval plan status |
| `agent_search` | `{ type, iteration, tools, message }` | Shows tools being called |
| `observation` | `{ type, iteration, tool_results, total_chunks }` | Shows chunks found |
| `agent_verify` | `{ type, iteration, sufficient, missingFields }` | Shows evidence sufficiency |
| `agent_replan` | `{ type, iteration, replanCount, missingFields }` | Shows bounded evidence replan |
| `agent_synthesize` | `{ type, message }` | Shows final-answer generation status |
| `fast_path` | `{ type, intent, message }` | Shows immediate response |
| `connected` | `{ type: "connected", status: "connected" }` | Initial stream handshake |

### Agent Metadata

Chat messages now include optional `agentMetadata`:

```typescript
interface MeetingChatMessage {
  // ... existing fields
  agentMetadata?: {
    iterations?: number;      // Number of agent iterations used
    replans?: number;          // Number of evidence replans used
    toolCalls?: string[];     // Tools called during processing
    agentThoughts?: string[]; // Agent reasoning messages
    intent?: string;           // Sanitized plan intent
    sections?: string[];       // Planned JSON sections
    missingFields?: string[];  // Fields still missing during verification
    evidenceCount?: number;    // Accumulated evidence count
  };
}
```

Agent SSE handling is defensive: `agent_search`, `observation`, and `agent_synthesize` events may arrive with only structured fields such as `tools`, `resultCount`, or `forced`, so `useMeetingWorkspace` derives a safe Vietnamese status message instead of assigning `undefined` into chat message content. The backend stream handshake also sends a typed JSON payload (`type: "connected"`), while the markdown/typewriter renderer treats missing message content as an empty string so one malformed transient streaming message cannot crash the chat thread.

### UI Components

| Component | Feature |
|-----------|---------|
| `ChatMessageBubble` | Shows fast path badge for immediate responses |
| `ChatMessageBubble` | Shows agent iteration badge during processing |
| `ChatMessageBubble` | Shows tools called section with badges |

### CSS Classes

| Class | Purpose |
|-------|---------|
| `.fast-path-badge` | Green badge for fast path responses |
| `.agent-iteration-badge` | Blue badge showing iteration count |
| `.agent-tools` | Container for tool badges |
| `.agent-tool-badge` | Individual tool badges |
| `.chat-message--fast-path` | Left border highlight for fast path |

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

*Document reflects project state during **Phase 36 Frontend V2 Intelligence Rendering**. Frontend source follows feature-layer boundaries and renders generic v2 records with transcript/playback seeking while backend remains the evidence source of truth.*
