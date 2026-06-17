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
    ├── layouts/
    │   └── AppShell.tsx
    ├── components/
    │   └── IconButton.tsx
    ├── styles/
    │   └── global.css
    └── features/
        ├── admin/
        │   ├── api/
        │   │   └── adminApi.ts
        │   ├── components/
        │   │   ├── AdminMetricsGroup.tsx
        │   │   ├── AdminSummaryCards.tsx
        │   │   └── AdminTargetsTable.tsx
        │   ├── dtos/
        │   │   └── adminDtos.ts
        │   ├── hooks/
        │   │   └── useAdminDashboard.ts
        │   ├── screens/
        │   │   └── AdminDashboardScreen.tsx
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

Routes are thin. The `auth`, `meetings`, and `admin` features own their API calls, response mapping, orchestration hooks, screen composition, feature-only components, and feature types.

## Runtime

The frontend is a Vite React TypeScript app. In Compose, it runs as an internal-only service on port `5173`. The Docker image installs dependencies with `npm ci` from `package-lock.json`.

Traffic path:

```text
browser -> NGINX / -> frontend:5173
browser -> NGINX /api/ -> backend:8000
```

The frontend service is not host-published. The public local URL remains:

```text
http://127.0.0.1:8080
```

## Meeting Workspace UI

`AppRoutes` gates the application behind backend-owned authentication. If no valid bearer token/account is available, it renders `AuthScreen` with login/register tabs. After login/register, the frontend stores the local session token in `localStorage`, calls `GET /api/me`, and passes the authenticated account/token into the app shell and feature hooks.

`AuthScreen` performs lightweight UX validation for email, required name, and minimum password length before calling the backend. Backend validation remains authoritative; `authApi` parses FastAPI validation errors and safe backend error payloads into user-visible messages instead of showing a generic request failure.

`MeetingsScreen` composes the implemented meeting workspace:

| Area | Component | Purpose |
|---|---|---|
| Account storage | `AccountFileLibrary` | Lists files uploaded by the authenticated account, supports authorized playback, blocks deleting linked meeting files, and deletes unlinked files |
| Meeting creation | `MeetingCreateForm` | Creates a meeting shell |
| Left sidebar | `MeetingList`, `MeetingCreateForm`, `AccountFileLibrary` | Lists meetings, creates a new analysis, and manages account-scoped uploaded files |
| Meeting actions | `MeetingActionPanel` | Shows the selected meeting, one-file upload/record controls, process/retry button, processing progress, and admin-only delete action |
| Audio playback | `MeetingAssetPlaybackPanel` | Shows the uploaded audio asset in a browser audio player above the processed JSON when the ready meeting has an audio file |
| Processed JSON result | `MeetingIntelligenceResultPanel` | Renders the complete `meeting-intelligence-result.v1` as readable collapsible sections |
| Meeting chat | `MeetingChatPanel` | Sits below the processed result, asks questions against a ready meeting, and renders saved answers, evidence state, and citations |
| Status display | `StatusPill` | Displays meeting and job state |

## Admin Dashboard UI

The dashboard view is reachable from the app shell navbar only for authenticated `Admin` accounts. The frontend still calls only backend APIs:

```text
Dashboard button -> AdminDashboardScreen -> useAdminDashboard -> adminApi -> GET /api/admin/metrics
```

The dashboard auto-refreshes every 30 seconds and renders:

| Area | Source |
|---|---|
| Summary cards | Backend-normalized health, target counts, and Redis cache state |
| Target table | Prometheus target health returned by the backend |
| Metric groups | Application, worker, container, database, cache, queue, storage, vector, and gateway metrics returned by the backend |

The browser never calls Prometheus directly and does not contain PromQL. Admin authorization, Prometheus querying, normalization, and Redis caching remain backend responsibilities. Hiding the dashboard button for non-admin users is UX only; backend still returns `403 admin_access_required`.

The recording entry point uses `MediaRecorder` to produce a completed `audio/webm` file and uploads it through the same asset endpoint as normal file uploads. It is not live transcription.

`MeetingActionPanel` follows the one-analysis-per-meeting rule. Upload and recording are shown only while the selected meeting is `DRAFT` and has no asset. Once a file is uploaded, the intake box is hidden and the meeting is locked to that asset whether processing later succeeds or fails. Processing remains available for an uploaded asset and retryable after a failed job. These controls are UI affordances only; backend state validation remains authoritative and returns `409 Conflict` for stale or direct requests that try to upload another file.

The central workspace no longer uses operation/chat tabs. It is a chatbot-style flow: progress and process controls at the top, uploaded audio playback above the processed JSON when an audio asset exists, processed JSON result sections in the middle after `READY`, and the meeting chat composer/thread below the result. The left sidebar behaves like a modern chat app history rail for selecting or creating analyses.

The current visual system uses a neutral operational surface, white raised panels, and multiple restrained accents: green for primary actions/ready states, indigo for queued states, amber for in-progress or partial states, and coral for destructive/error states. Cards and controls keep the existing 8px radius limit while using slightly stronger spacing, panel shadows, and focus states for a more modern workspace feel.

## API And DTO Boundaries

`authApi.ts`, `meetingApi.ts`, and `adminApi.ts` are intentionally thin. They send requests to backend endpoints and attach `Authorization: Bearer <token>` for authenticated calls.

`meetingDtos.ts` maps backend snake_case responses into frontend camelCase types and performs basic runtime shape checks.

Meeting chat calls are handled through the same feature boundary:

```text
MeetingChatPanel -> useMeetingWorkspace -> meetingApi -> /api/meetings/{meetingId}/chat
```

Chat request building and response/history mapping live in `meetingDtos.ts`. The frontend keeps only lightweight UI state: current question text, current chat session ID, and the message list returned by the backend. After an answer is submitted, the hook reloads persisted chat history through `GET /api/meetings/{meetingId}/chat/{sessionId}` so the displayed thread comes from backend state.

Assistant messages display the backend evidence state and citations. Citations include processed JSON section pointers, transcript time ranges when available, and the citation text returned by the backend. Unsupported answers are shown as normal assistant messages with the backend `not_enough_evidence` state rather than optimistic certainty.

For selected meetings, the hook loads `GET /api/meetings/{meetingId}/processing-status` to retrieve the latest job and latest asset, then loads `GET /api/meetings/{meetingId}/intelligence-result` when the meeting is `READY`. When the latest asset is an audio file, the hook fetches `GET /api/meetings/{meetingId}/assets/{assetId}/content` with the bearer token, creates a temporary browser Blob URL, and revokes it when the selected meeting or asset changes. While a meeting is `QUEUED` or `PROCESSING`, the hook polls processing status every 3 seconds. The frontend does not parse or recompute intelligence sections; it renders the JSON returned by the backend.

The account file library calls `/api/files` through the meetings feature API layer. It can upload account files, fetch authorized file bytes into a temporary Blob URL for playback/download, and ask the backend to delete unlinked files. Files linked to an existing meeting session show disabled delete behavior in the UI, but backend conflict responses remain authoritative.

Admin meeting deletion is exposed as an admin-only UI affordance in `MeetingActionPanel`. It calls `DELETE /api/admin/meetings/{meetingId}` through the meeting API wrapper with the current bearer token, then reloads meeting and file-library state.

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

Earlier phase screenshots were generated under ignored `tmp/screenshots/`.

Playwright screenshot re-verification was attempted on 2026-06-17, but the local Playwright package could not install Chromium because the current environment reports `ubuntu26.04-x64`, which Playwright did not support for that browser build. The verified fallback for this UI pass is TypeScript/Vite build plus gateway HTTP smoke.

*Document reflects project state after Phase 7 hardening verification on **2026-06-17**. Frontend is implemented for backend-owned register/login/logout/me, local bearer-token session storage, account-aware app shell, Admin/User role display, admin-only dashboard navigation, admin-only meeting delete affordance, account file library upload/play/delete, linked-file delete blocking UX, meeting upload/status, one-file intake locking, browser recording upload, processing progress, authenticated uploaded-audio playback, processed JSON section rendering, and meeting-scoped chat UI with citations. Backend authorization remains authoritative.*
