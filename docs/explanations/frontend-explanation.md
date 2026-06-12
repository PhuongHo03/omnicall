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
                ├── DevContextPanel.tsx
                ├── MeetingActionPanel.tsx
                ├── MeetingChatPanel.tsx
                ├── MeetingCreateForm.tsx
                ├── MeetingList.tsx
                └── StatusPill.tsx
```

The frontend follows the feature-based layered structure:

```text
URL -> route -> feature screen -> feature hook -> DTO/API -> backend
```

Routes are thin. The `meetings` feature owns its API calls, response mapping, orchestration hook, screen composition, feature-only components, and feature types.

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

`MeetingsScreen` composes the implemented meeting workspace:

| Area | Component | Purpose |
|---|---|---|
| Development context | `DevContextPanel` | Sends `X-User-ID`, `X-Workspace-ID`, and optional bootstrap headers |
| Meeting creation | `MeetingCreateForm` | Creates a meeting shell |
| Meeting list | `MeetingList` | Lists workspace meetings and selects one |
| Meeting actions | `MeetingActionPanel` | Uploads files, records browser audio, queues processing, refreshes status |
| Meeting chat | `MeetingChatPanel` | Asks questions against a ready meeting and renders saved answers, evidence state, and citations |
| Status display | `StatusPill` | Displays meeting and job state |

The recording entry point uses `MediaRecorder` to produce a completed `audio/webm` file and uploads it through the same asset endpoint as normal file uploads. It is not live transcription.

The main workspace detail area uses tabs for operations and chat. The chat tab is enabled only for meetings whose backend status is `READY`; this is a UI affordance only, and the backend still validates state and permissions.

## API And DTO Boundaries

`meetingApi.ts` is intentionally thin. It sends requests to backend endpoints and attaches the development auth headers from UI state.

`meetingDtos.ts` maps backend snake_case responses into frontend camelCase types and performs basic runtime shape checks.

Meeting chat calls are handled through the same feature boundary:

```text
MeetingChatPanel -> useMeetingWorkspace -> meetingApi -> /api/meetings/{meetingId}/chat
```

Chat request building and response/history mapping live in `meetingDtos.ts`. The frontend keeps only lightweight UI state: current question text, current chat session ID, and the message list returned by the backend. After an answer is submitted, the hook reloads persisted chat history through `GET /api/meetings/{meetingId}/chat/{sessionId}` so the displayed thread comes from backend state.

Assistant messages display the backend evidence state and citations. Citations include processed JSON section pointers, transcript time ranges when available, and the citation text returned by the backend. Unsupported answers are shown as normal assistant messages with the backend `not_enough_evidence` state rather than optimistic certainty.

The frontend does not enforce business rules. Backend remains authoritative for authorization, upload validation, state transitions, idempotency, and processing eligibility.

## Verification

Verified commands:

```bash
npm run build
docker compose --env-file .env.example up -d --build frontend nginx
docker compose --env-file .env.example exec -T frontend npm run build
docker compose --env-file .env.example build frontend
curl -i http://127.0.0.1:8080/
```

Playwright verification:

| Check | Result |
|---|---|
| Desktop screenshot at `1440x900` | Passed |
| Mobile screenshot at `390x844` | Passed |
| UI smoke: create meeting, upload `.wav`, process, see `QUEUED` | Passed |
| Phase 5 chat UI TypeScript/Vite build | Passed |
| Gateway frontend response after chat UI wiring | `200` |

Screenshots were generated under ignored `tmp/screenshots/`.

*Document reflects project state at **Phase 5 - Retrieval And Chat** complete. Frontend is implemented for local meeting upload/status, processing controls, and meeting-scoped chat UI with citations. Production authentication remains planned.*
