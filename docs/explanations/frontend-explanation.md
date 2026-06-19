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
    │   │   └── IconButton.tsx
    │   ├── layouts/
    │   │   └── AppShell.tsx
    │   └── styles/
    │       └── global.css
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
        │   │   └── useAdminMetrics.ts
        │   ├── screens/
        │   │   ├── AdminAccountsScreen.tsx
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
            │   └── meetingApi.ts
            ├── dtos/
            │   └── meetingDtos.ts
            ├── hooks/
            │   └── useMeetingWorkspace.ts
            ├── screens/
            │   └── MeetingsScreen.tsx
            ├── types/
            │   └── meetingTypes.ts
            └── components/
                ├── AccountFileLibrary.tsx
                ├── MeetingActionPanel.tsx
                ├── MeetingAssetPlaybackPanel.tsx
                ├── MeetingChatPanel.tsx
                ├── MeetingCreateForm.tsx
                ├── MeetingIntelligenceResultPanel.tsx
                ├── MeetingList.tsx
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
| Account storage | `AccountFileLibrary` | Lists files uploaded by the authenticated account, supports authorized playback, blocks deleting linked meeting files, and deletes unlinked files |
| Meeting creation | `MeetingCreateForm` | Creates a meeting shell |
| Left sidebar | `MeetingList`, `MeetingCreateForm`, `AccountFileLibrary` | Lists meetings, creates a new analysis, and manages account-scoped uploaded files |
| Meeting actions | `MeetingActionPanel` | Shows the selected meeting, one-file upload/record controls, process/retry button, processing progress, and admin-only delete action |
| Audio playback | `MeetingAssetPlaybackPanel` | Shows the uploaded audio asset in a browser audio player above the processed JSON when the ready meeting has an audio file |
| Processed JSON result | `MeetingIntelligenceResultPanel` | Renders the complete `meeting-intelligence-result.v1` as readable collapsible sections and remembers each section's open/closed UI preference in browser storage |
| Meeting chat | `MeetingChatPanel` | Sits below the processed result, asks questions against a ready meeting, and renders saved answers, evidence state, and citations |
| Status display | `StatusPill` | Displays meeting and job state |

Meeting selection is URL-backed. `/meetings` is the authenticated landing page and intentionally keeps no meeting selected. Opening `/meetings/:meetingId` selects that meeting after the authorized meeting list loads. Selecting or creating a meeting updates the URL, deleting the selected meeting returns to `/meetings`, and clicking the navbar Meetings button always returns to `/meetings`. This supports refresh, browser back/forward navigation, bookmarks, and direct links without moving business authorization into the frontend.

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

`MeetingActionPanel` follows the one-analysis-per-meeting rule. Upload and recording are shown only while the selected meeting is `DRAFT` and has no asset. Once a file is uploaded, the intake box is hidden and the meeting is locked to that asset whether processing later succeeds or fails. Processing remains available for an uploaded asset and retryable after a failed job. These controls are UI affordances only; backend state validation remains authoritative and returns `409 Conflict` for stale or direct requests that try to upload another file.

The central workspace no longer uses operation/chat tabs. It is a chatbot-style flow: progress and process controls at the top, uploaded audio playback above the processed JSON when an audio asset exists, processed JSON result sections in the middle after `READY`, and the meeting chat composer/thread below the result. The processed JSON panel remembers open/closed section state locally in the browser so switching meetings does not force `Summary`, `Analysis`, or `Quality` back open after the user closes them. The left sidebar behaves like a modern chat app history rail for selecting or creating analyses.

The current visual system uses a neutral operational surface, white raised panels, and multiple restrained accents: green for primary actions/ready states, indigo for queued states, amber for in-progress or partial states, and coral for destructive/error states. Cards and controls keep the existing 8px radius limit while using slightly stronger spacing, panel shadows, and focus states for a more modern workspace feel.

## API And DTO Boundaries

`authApi.ts`, `meetingApi.ts`, and `adminApi.ts` are intentionally thin. They send requests to backend endpoints and attach `Authorization: Bearer <token>` for authenticated calls.

`meetingDtos.ts` maps backend snake_case responses into frontend camelCase types and performs basic runtime shape checks.

Meeting chat calls are handled through the same feature boundary:

```text
MeetingChatPanel -> useMeetingWorkspace -> meetingApi -> /api/meetings/{meetingId}/chat
```

Chat request building and response/history mapping live in `meetingDtos.ts`. The frontend keeps only lightweight UI state: current question text and the message list returned by the backend. It does not create, store, or send a chat-session ID. After an answer is submitted, and whenever a `READY` meeting is selected or refreshed, the hook reloads persisted chat history through `GET /api/meetings/{meetingId}/chat`, so the displayed thread always comes from backend state and survives browser reloads.

Assistant messages display the backend evidence state and citations. Citations include processed JSON section pointers, transcript time ranges when available, and the citation text returned by the backend. Unsupported answers are shown as normal assistant messages with the backend `not_enough_evidence` state rather than optimistic certainty.

For selected meetings, the hook loads `GET /api/meetings/{meetingId}/processing-status` to retrieve the latest job and latest asset, then loads `GET /api/meetings/{meetingId}/intelligence-result` when the meeting is `READY`. When the latest asset is an audio file, the hook fetches `GET /api/meetings/{meetingId}/assets/{assetId}/content` with the bearer token, creates a temporary browser Blob URL, and revokes it when the selected meeting or asset changes. While a meeting is `QUEUED` or `PROCESSING`, the hook polls processing status every 3 seconds. The frontend does not parse or recompute intelligence sections; it renders the JSON returned by the backend.

The account file library calls `/api/files` through the meetings feature API layer. It can upload account files, fetch authorized file bytes into a temporary Blob URL for playback/download, and ask the backend to delete unlinked files. Files linked to an existing meeting session show disabled delete behavior in the UI, but backend conflict responses remain authoritative.

Admin meeting deletion is exposed as an admin-only UI affordance in `MeetingActionPanel`. It asks for in-app confirmation before calling `DELETE /api/admin/meetings/{meetingId}` through the meeting API wrapper with the current bearer token, then reloads meeting and file-library state.

Destructive UI actions ask for confirmation before sending requests: account-file delete in `AccountFileLibrary`, meeting-session delete in `MeetingActionPanel`, and account delete in `AdminAccountsTable`. These confirmations use the shared in-app `ConfirmDialog` component instead of browser-native `window.confirm`, so the browser cannot suppress later confirmations with a "don't ask again" option. These confirmations are UX guardrails only; backend authorization and reference checks remain authoritative.

The frontend does not enforce business rules. Backend remains authoritative for authorization, upload validation, state transitions, idempotency, and processing eligibility.

## Verification

Verified commands:

```bash
npm run build
docker compose --env-file .env.example up -d --build frontend nginx
docker compose --env-file .env.example exec -T frontend npm run build
docker compose --env-file .env.example build frontend
docker compose --env-file .env exec -T frontend npm run build
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
| Admin account role-management TypeScript/Vite build | Passed |
| Gateway smoke for default User registration and admin role management | Passed |
| Account delete + destructive confirmation TypeScript/Vite build | Passed |
| Backend full suite after account deletion hardening | `75` tests passed |
| Shared folder refactor and in-app confirm dialog TypeScript/Vite build | Passed |
| React Router route split and admin metrics/accounts separation build | Passed |
| Navbar account hover dropdown and meeting account-banner removal build | Passed |
| Phase 8 Admin logs TypeScript/Vite build and NGINX route smoke | Passed |

Earlier phase screenshots were generated under ignored `tmp/screenshots/`.

Playwright screenshot re-verification was attempted on 2026-06-17, but the local Playwright package could not install Chromium because the current environment reports `ubuntu26.04-x64`, which Playwright did not support for that browser build. The verified fallback for this UI pass is TypeScript/Vite build plus gateway HTTP smoke.

*Document reflects project state after Phase 8 operational-log verification on **2026-06-19**. Frontend routes now include Admin-only metrics, accounts, and realtime processing/RAG logs, while the previously verified auth, meeting workspace, file library, processed JSON, playback, deletion, and cited chat behavior remains unchanged. Backend authorization remains authoritative.*
