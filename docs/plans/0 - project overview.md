# Project Overview

## Tech Stack

- Frontend: React, TypeScript, Vite.
- Backend API: Python, FastAPI.
- Worker: Python worker process, Celery worker/Beat, RabbitMQ.
- Database: PostgreSQL.
- Cache: Redis.
- Object storage: MinIO.
- Vector database: Milvus.
- Gateway: NGINX.
- Monitoring: Prometheus.

## Product Definition

Omnicall is a meeting intelligence chatbot. It turns uploaded or recorded meeting content into a rich processed transcript JSON result, then lets users ask questions grounded primarily in that processed meeting intelligence.

The processed transcript JSON is the core product artifact. It can include the transcript and all derived results in one versioned document. The system may still create normalized database rows or vector chunks from that JSON for indexing and retrieval, but the product-facing result does not have to split transcript and analysis into separate artifacts.

MVP product promise:

- Ingest a meeting file or browser recording.
- Extract a complete processed transcript JSON containing transcript, summaries, analysis, results, timeline, notes, action items, risks, and other meeting intelligence.
- Let users ask questions about one processed meeting.
- Return answers based on processed insights first, with citations back to transcript ranges or insight records.
- Keep original files, processing state, analysis output, and chat history traceable.

Primary user flows:

| Flow | User Goal | System Outcome |
|---|---|---|
| Account access | Register or login to Omnicall | Backend creates or validates the account and returns authenticated account context with `Admin` or `User` role |
| Account administration | Promote or demote local accounts | Admin dashboard lists accounts and changes another account's role while preventing self-role changes |
| Account deletion | Remove a local account | Admin-only backend flow deletes another account, blocks self-deletion, blocks active processing races, revokes queued jobs by ID, invalidates admin metrics cache, and cascades cleanup to target-owned sessions, meetings, and stored files |
| Upload meeting | Add one existing audio/video file, transcript, or meeting notes file to a meeting | Private object is stored, metadata is saved, and the meeting is locked to that file for one analysis lineage |
| Record meeting | Capture a live meeting from the browser | Recording is uploaded as the meeting asset and enters the same processing pipeline |
| Review analysis | Understand what happened without replaying the whole meeting | Complete processed transcript result is displayed |
| Ask meeting chat | Retrieve precise information from the processed result | Frontend chat asks the backend below the processed JSON result, which answers from processed intelligence first and cites transcript evidence |
| Manage uploaded files | Review files uploaded by the current account | Account-scoped file library lists owned uploads, allows playback, and allows deletion only when the file is not linked to an existing meeting session |
| Delete meeting session | Remove an analysis session and its linked artifacts | Admin-only backend flow deletes the meeting session and cascades cleanup to linked file bytes, metadata, processed result, retrieval data, and chat history |
| Monitor operations | See system health and processing state | Admin dashboard reads normalized backend metrics |
| Inspect operational logs | Follow processing and RAG steps in realtime | Admin logs page tails temporary structured Redis events with provider/model and safe error details |

Frontend route map:

| Route | Purpose |
|---|---|
| `/auth` | Login and registration tabs on one account-access screen |
| `/meetings` | Default authenticated landing page with no selected meeting |
| `/meetings/:meetingId` | Direct URL for one selected meeting |
| `/admin/metrics` | Default admin portal page for operations metrics |
| `/admin/accounts` | Admin account and role management |
| `/admin/logs` | Admin-only realtime processing and RAG operational logs |

`/` redirects authenticated accounts to `/meetings`; the navbar Meetings action also returns to `/meetings`. `/admin` redirects to `/admin/metrics`. The right-side Admin Portal dropdown is rendered only for `Admin`, while route guards redirect unauthenticated users to `/auth` and non-admin users away from `/admin/*`.

Out of MVP unless explicitly pulled forward:

- Cross-meeting workspace chat.
- Real-time partial transcription.
- External task-tool sync.
- Advanced speaker diarization correction UI.
- SSO and enterprise policy management.

## Core Domain Concepts

Durable business state belongs in PostgreSQL.

| Concept | Purpose |
|---|---|
| `user` | Account identity |
| `account_session` | Backend-owned bearer login session |
| `audit_event` | Security and operational trace for important actions |
| `meeting` | Main aggregate for uploaded/recorded meeting content |
| `meeting_asset` | File metadata for raw uploads, recordings, transcripts, exports, and standalone account-library files stored in MinIO |
| `processing_job` | Async job state for transcription, analysis, and embedding work |
| `meeting_intelligence_result` | Versioned processed transcript JSON used as the main knowledge base for chat |
| `meeting_chunk` | Retrieval unit derived from processed JSON sections and source ranges |
| `chat_message` | Saved user questions, assistant answers, citations, and timestamps |

The current PostgreSQL local-dev schema intentionally has 9 business tables: `users`, `account_sessions`, `audit_events`, `meetings`, `meeting_assets`, `processing_jobs`, `meeting_intelligence_results`, `meeting_chunks`, and `chat_messages`. `workspaces`, `workspace_members`, `account_files`, `transcript_segments`, `meeting_insights`, and `chat_sessions` were removed during the schema consolidation; their responsibilities are handled by direct account ownership, JSONB result storage, derived `meeting_chunks`, and meeting-scoped chat messages.

Meeting status lifecycle:

```text
DRAFT -> UPLOADED -> QUEUED -> PROCESSING -> READY
                              -> FAILED -> QUEUED (retry)
```

Processing job status lifecycle:

```text
PENDING -> RUNNING -> SUCCEEDED
        -> CANCELLED
RUNNING -> FAILED -> RETRYING -> RUNNING
```

`PENDING` jobs whose meeting remains `QUEUED` beyond the configured stale threshold are automatically republished by Celery Beat. `FAILED` jobs still require an explicit retry.

## Meeting Intelligence Pipeline

Core asynchronous pipeline:

```text
upload/recording
-> backend validation
-> MinIO object
-> PostgreSQL asset + processing_job
-> RabbitMQ task
-> worker lock + idempotency check
-> text extraction or voice preprocessing
-> VAD + ASR + diarization when the source is voice
-> transcript segment contract
-> processed transcript JSON generation
-> schema validation, quality checks, and source linking
-> JSON-section chunking
-> embedding generation
-> PostgreSQL retrieval chunk persistence
-> Milvus vector upsert
-> PostgreSQL status update
```

The current backend slice persists retrieval chunks in PostgreSQL first, generates model-backed local embeddings through Ollama, then upserts derived vectors into Milvus. PostgreSQL chunk records stay authoritative and are reloaded after vector search.

Chat retrieval flow:

```text
question
-> backend permission check
-> query normalization
-> query embedding
-> vector search in Milvus
-> load authoritative processed JSON sections/chunks
-> evidence guard against irrelevant local-embedding hits
-> rerank candidate chunks when rerank provider is enabled
-> load source evidence from transcript entries inside the JSON
-> guardrail input/context checks when guardrails are enabled
-> answer generation with cited context
-> guardrail output check when guardrails are enabled
-> save chat messages
-> response with answer + citations
```

Processed transcript JSON categories:

| Category | Meaning |
|---|---|
| Executive summary | Short, high-signal overview of the meeting outcome |
| Detailed summary | Structured summary by topic or agenda section |
| Key points | Important points worth remembering |
| Decisions | Explicit or strongly implied decisions, with confidence and source evidence |
| Action items | Tasks with owner, due date, priority, status, and source evidence when available |
| Important notes | Items users should remember even if they are not tasks or decisions |
| Timeline and milestones | Dates, deadlines, follow-up checkpoints, release targets, or time-sensitive commitments |
| Risks and blockers | Risks, blockers, uncertainties, dependencies, and mitigation notes |
| Open questions | Questions raised but not resolved |
| Follow-ups | People, teams, or topics that require later confirmation |
| Topics | Thematic grouping for navigation and retrieval |
| Entities | People, teams, products, customers, projects, or systems mentioned |
| Important quotes | Short cited excerpts only when useful for traceability |

Additional useful sections:

| Category | Meaning |
|---|---|
| Participants | Speakers, attendees, roles, teams, or inferred participants |
| Agenda | Planned or inferred agenda items |
| Outcomes | Final meeting outcomes, conclusions, or agreed direction |
| Requirements | Business, product, technical, or operational requirements mentioned |
| Constraints | Budget, timeline, technical, staffing, legal, or process constraints |
| Assumptions | Assumptions made during discussion that may need validation |
| Dependencies | External teams, systems, vendors, tasks, or decisions needed before progress |
| Blockers | Items currently preventing progress |
| Conflicts | Disagreements, tradeoffs, or competing options discussed |
| Metrics | Numbers, KPIs, targets, estimates, or thresholds mentioned |
| Customer/user feedback | Customer problems, user requests, objections, or satisfaction signals |
| Decisions pending approval | Items tentatively agreed but requiring confirmation |
| Parking lot | Important topics deferred for later |
| Glossary | Domain terms, acronyms, product names, or internal shorthand |
| Sentiment and tone | Optional high-level meeting tone, tension, urgency, or confidence signals |
| Quality warnings | Missing audio, unknown speaker, low confidence, contradictory statements, or incomplete sections |

Processed JSON draft:

```json
{
  "schemaVersion": "meeting-intelligence-result.v1",
  "meeting": {
    "id": "meeting-id",
    "title": "Meeting title",
    "startedAt": "2026-06-12T09:00:00Z",
    "durationSeconds": 3600
  },
  "source": {
    "assetIds": ["asset-id"],
    "transcriptionProvider": "provider-name",
    "analysisProvider": "provider-name",
    "generatedAt": "2026-06-12T10:30:00Z"
  },
  "participants": [],
  "transcript": {
    "segments": [
      {
        "id": "seg-001",
        "speaker": "Speaker 1",
        "startMs": 0,
        "endMs": 12000,
        "text": "Transcript text",
        "confidence": 0.92
      }
    ]
  },
  "summary": {
    "executive": "",
    "detailed": [],
    "keyPoints": []
  },
  "analysis": {
    "topics": [],
    "decisions": [],
    "actionItems": [],
    "importantNotes": [],
    "timeline": [],
    "risks": [],
    "blockers": [],
    "dependencies": [],
    "openQuestions": [],
    "followUps": [],
    "outcomes": [],
    "requirements": [],
    "constraints": [],
    "assumptions": [],
    "conflicts": [],
    "metrics": [],
    "parkingLot": [],
    "entities": [],
    "glossary": []
  },
  "citations": [
    {
      "id": "cite-001",
      "segmentIds": ["seg-001"],
      "startMs": 0,
      "endMs": 12000
    }
  ],
  "quality": {
    "coverage": "complete",
    "warnings": [],
    "confidence": 0.86
  }
}
```

Processed JSON quality requirements:

- Every structured item should include citation IDs or source transcript segment IDs when evidence exists.
- Important items should include confidence or extraction quality where useful.
- Action items should separate `owner`, `task`, `dueDate`, `priority`, and `status` instead of storing only prose.
- Timeline items should normalize dates when possible while preserving original wording.
- Risks should distinguish blocker, dependency, uncertainty, and mitigation if present.
- Chat retrieval should prefer structured JSON sections over plain transcript text.
- Transcript entries inside the JSON remain available for audit, source citations, and fallback retrieval.

## Model Provider Strategy

Model integrations must sit behind provider interfaces. The backend and worker own model calls; the frontend never calls model providers directly and never receives provider secrets.

Model groups:

| Group | Role | Purpose |
|---|---|---|
| Voice | ASR | Convert meeting audio into transcript text |
| Voice | Speaker embedding | Extract speaker identity vectors for diarization, e.g. WeSpeaker |
| Voice | VAD/segmentation | Detect speech regions and prepare windows for ASR/diarization |
| Text | LLM | Generate processed transcript JSON and answer chat questions |
| Text | Embedding | Embed processed JSON sections for vector search |
| Text | Rerank | Rerank retrieved chunks before answer generation |
| Safety | Guardrail | Classify and control unsafe prompts, transcript content, retrieved context, and generated answers |

LLM provider priority:

```text
1. External API provider
2. Private OpenAI-compatible or custom LLM endpoint
3. Ollama local fallback with a small model
```

LLM usage rules:

- The same `LLMProvider` interface should support API providers, private endpoints, and Ollama.
- The provider must be selected by environment variables, not hardcoded in services.
- Private server endpoints should be treated as first-class providers, not temporary hacks.
- Ollama is the default local fallback path for development and degraded operation.
- Ollama fallback should use a small local model and may produce lower-quality JSON; schema validation remains mandatory.
- Generation of `meeting_intelligence_result` JSON should prefer the best available API/endpoint model.
- Chat answer generation can use a cheaper/faster model first and escalate to a stronger provider for difficult or low-confidence questions.
- Provider prompts, raw provider responses, and secrets must not be exposed to the frontend.

Model placement rules:

- Voice ASR and speaker embedding/diarization run locally through configured model commands or wrappers.
- VAD is local signal processing and is not counted as one of the six model slots.
- Text embeddings run through the local Ollama embedding model.
- Rerank runs through a configured local reranker model command.
- Guardrails run through local Ollama.
- Only the LLM provider may use an external API or private endpoint.

Implemented provider configuration keys:

```text
LLM_PROVIDER=api|endpoint|ollama
LLM_API_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL=...
LLM_ENDPOINT_COMPATIBILITY=openai|custom-json
LLM_TIMEOUT_SECONDS=60
OLLAMA_LLM_TIMEOUT_SECONDS=600
OLLAMA_CONTEXT_LENGTH=8192
PROCESSING_RECONCILIATION_INTERVAL_SECONDS=60
PROCESSING_RECONCILIATION_STALE_SECONDS=120
PROCESSING_RECONCILIATION_BATCH_SIZE=100
LLM_FALLBACK_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:1.5b

ASR_TIMEOUT_SECONDS=120
ASR_TIMEOUT_REALTIME_FACTOR=1.0
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768
EMBEDDING_TIMEOUT_SECONDS=30
VECTOR_PROVIDER=milvus
MILVUS_HOST=milvus
MILVUS_PORT=19530
MILVUS_COLLECTION=meeting_chunks
RERANK_TOP_K=12
RERANK_OUTPUT_K=6
RERANK_TIMEOUT_SECONDS=30

VAD_MIN_SPEECH_MS=300
VAD_SILENCE_GAP_MS=500
VAD_ENERGY_THRESHOLD=0.012

GUARDRAIL_MODEL=llama-guard3:1b
GUARDRAIL_TIMEOUT_SECONDS=20
GUARDRAIL_MAX_RETRIES=0
GUARDRAIL_INPUT_ENABLED=true
GUARDRAIL_TRANSCRIPT_ENABLED=true
GUARDRAIL_CONTEXT_ENABLED=true
GUARDRAIL_OUTPUT_ENABLED=true
GUARDRAIL_STRICT_MODE=false
```

ASR, diarization, and rerank commands, model snapshots, CPU device selection, `int8` ASR compute mode, `/models` mount path, ffmpeg binary, and temporary voice work directory are repository-owned runtime contracts. They are intentionally not environment variables because changing any of them requires a coordinated image/code change. `ollama-init` derives its pull list from `OLLAMA_MODEL`, `EMBEDDING_MODEL`, and `GUARDRAIL_MODEL`, avoiding a duplicate bootstrap-list variable.

Local model defaults for the completed Phase 5.5 and 5.6 scope:

| Phase | Role | Default Local Direction | Notes |
|---|---|---|---|
| 5.5 | Audio preprocessing and VAD | ffmpeg normalization to 16 kHz mono WAV plus local energy VAD | Implemented as voice preparation before ASR |
| 5.5 | ASR | `faster-whisper` CPU `int8` runner over `/models/asr` | Local-only; default command is `python -m backend.model_runners.asr` |
| 5.5 | Speaker embedding/diarization | WeSpeaker runner over `/models/diarization` | Local-only; default command is `python -m backend.model_runners.diarization` |
| 5.5 | Text embedding | `nomic-embed-text` through local Ollama | 768-dimensional embedding; no hash embedding in production |
| 5.5 | Rerank | `bge-reranker-v2-m3` through SentenceTransformers cross-encoder runner over `/models/rerank` | If unavailable, retrieval keeps original order and records rerank unavailable metadata |
| 5.6 | Guardrail | `llama-guard3:1b` through local Ollama | Implemented as default request-path local guardrail |
| 5.6 | Guardrail benchmark | `granite3-guardian:2b` through Ollama | Documented optional stronger risk/RAG judging candidate if latency is acceptable |

## MVP API Surface

Backend endpoints:

| Method | Path | Status | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | Implemented | Read backend health |
| `POST` | `/api/auth/login` | Implemented | Start authenticated session |
| `POST` | `/api/auth/register` | Implemented | Create a local account |
| `POST` | `/api/auth/logout` | Implemented | End session |
| `GET` | `/api/me` | Implemented | Read current user/session context |
| `POST` | `/api/meetings` | Implemented | Create a meeting shell named with its generated ID |
| `GET` | `/api/meetings` | Implemented | List meetings visible to the user |
| `GET` | `/api/meetings/{meetingId}` | Implemented | Read meeting detail and status |
| `PATCH` | `/api/meetings/{meetingId}` | Implemented | Rename an owned meeting |
| `POST` | `/api/meetings/{meetingId}/assets` | Implemented | Upload meeting file/recording asset, transcript, or notes text |
| `POST` | `/api/meetings/{meetingId}/process` | Implemented | Queue processing |
| `GET` | `/api/meetings/{meetingId}/processing-status` | Implemented | Read meeting/job progress |
| `GET` | `/api/meetings/{meetingId}/intelligence-result` | Implemented | Read the complete processed transcript JSON when needed |
| `POST` | `/api/meetings/{meetingId}/chat` | Implemented | Ask a meeting-grounded question |
| `GET` | `/api/meetings/{meetingId}/chat` | Implemented | Read the meeting-scoped chat history |
| `GET` | `/api/admin/metrics` | Implemented | Read normalized admin metrics through backend admin auth and Redis cache |
| `GET` | `/api/admin/accounts` | Implemented | List local accounts and role metadata for admin management |
| `PATCH` | `/api/admin/accounts/{userId}/role` | Implemented | Change another account's role between `Admin` and `User` |
| `DELETE` | `/api/admin/meetings/{meetingId}` | Implemented | Admin-only meeting session deletion with cascading cleanup |
| `GET` | `/api/files` | Implemented | List files uploaded by the current account |
| `POST` | `/api/files` | Implemented | Upload a reusable account-scoped file |
| `GET` | `/api/files/{fileId}/content` | Implemented | Play or download an owned uploaded file through backend authorization |
| `DELETE` | `/api/files/{fileId}` | Implemented | Delete an owned uploaded file only when not linked to an existing meeting session |

Frontend may validate input shape for UX, but backend must revalidate all uploads, permissions, and state transitions.

Current meeting intake rule: one meeting accepts only one uploaded or recorded asset. After that asset exists, upload/record controls are hidden in the frontend and the backend rejects different upload attempts with `409 meeting_already_has_asset`. A failed processing job can be retried against the same asset; a different file requires creating a new meeting.

## Project Structure

```text
.
├── AGENTS.md                         <- Project rules for AI/code sessions
├── README.md                         <- Project hub and quick navigation
├── docker-compose.yml                 <- Local runtime wiring
├── .env.example                      <- Runtime configuration template
├── .dockerignore                     <- Docker build context ignores
├── .gitignore                        <- Local artifact and secret ignores
├── backend/                          <- FastAPI backend service
│   ├── Dockerfile                    <- Backend container image
│   ├── configs/                      <- Runtime configuration
│   ├── controllers/                  <- HTTP route handlers
│   ├── dependencies/                 <- FastAPI dependencies such as auth context
│   ├── dtos/                         <- Request/response contracts
│   ├── migrations/                   <- Alembic migrations
│   ├── middlewares/                  <- Request/response middleware
│   ├── model_runners/                <- Local ASR, diarization, and rerank command runners
│   ├── models/                       <- SQLAlchemy database models
│   ├── providers/                    <- Storage, queue, lock, transcription, analysis, and LLM adapters
│   ├── repositories/                 <- Database access abstractions
│   ├── services/                     <- Business services/use cases
│   ├── tasks/                        <- Celery task definitions for worker entrypoints
│   ├── utils/                        <- Shared atomic utilities
│   ├── main.py                       <- FastAPI application entrypoint
│   ├── requirements.txt              <- Backend Python dependencies
│   └── requirements-dev.txt          <- Backend development/test dependencies
├── frontend/                         <- Vite React frontend service
│   ├── Dockerfile                    <- Frontend container image
│   ├── src/
│   │   ├── routes/                   <- Thin route composition
│   │   ├── shared/                   <- Shared components, layouts, styles, utilities, and assets
│   │   └── features/                 <- Auth, admin metrics/accounts, and meeting feature layers
│   └── package.json                  <- Frontend dependencies and scripts
├── infras/                           <- Infrastructure service config
│   ├── postgres/                     <- PostgreSQL runtime and client-auth config
│   ├── redis/                        <- Redis persistence and memory config
│   ├── rabbitmq/                     <- RabbitMQ runtime config and enabled plugins
│   ├── etcd/                         <- Single-node etcd persistence config
│   ├── milvus/                       <- Milvus standalone override config
│   ├── model-init/                   <- ASR/diarization/rerank model bootstrap
│   ├── docker-exporter/              <- Internal Docker stats exporter for Prometheus
│   ├── nginx/                        <- Gateway config
│   └── prometheus/                   <- Metrics scrape config
└── docs/
    ├── explanations/                 <- Source-derived area explanations
    ├── plans/                        <- Roadmap and phase checklists
    ├── rules/                        <- Project documentation rules
    └── PROJECT_PLAN.md               <- Planning index
```

## Architecture Rules

- Backend uses the layered structure already scaffolded under `backend/`.
- Frontend code uses feature-based layered structure:
  - Preserve Vite/React routing under `frontend/src/routes/`.
  - Put discrete business areas under `frontend/src/features/<feature>/`.
  - Keep cross-feature shared code under `frontend/src/shared/`, with subfolders such as `components`, `layouts`, `styles`, `utils`, and `assets` only when they contain real code/assets.
  - Add feature layers such as `api`, `dtos`, `hooks`, `screens`, `states`, `types`, and `components` only when they have real responsibility.
  - Keep routes thin, screens compositional, API calls in `api`, runtime validation/mapping in `dtos`, orchestration in `hooks`, reusable state transitions in `states`, and feature-only UI in feature `components`.

## Connection & Runtime Info

| Resource | Detail |
|---|---|
| Gateway health | `GET http://127.0.0.1:8080/health` through NGINX |
| Frontend app | `GET http://127.0.0.1:8080/` through NGINX |
| Backend health through gateway | `GET http://127.0.0.1:8080/api/health` |
| Local backend command | `uvicorn backend.main:app --reload` |
| Local Compose command | `docker compose up -d --build` |
| Migration command | `docker compose exec -T backend alembic upgrade head` |
| Worker command | `celery -A backend.configs.celery_app.celery_app worker --queues=meeting-processing,processing-maintenance` |
| Beat command | `celery -A backend.configs.celery_app.celery_app beat` |
| Env template | Root `.env.example` |
| Public URL | `http://127.0.0.1:8080` locally when `APP_BIND_IP=0.0.0.0` and `NGINX_PORT=8080` |
| Adminer | `http://127.0.0.1:8081` |
| MinIO Console | `http://127.0.0.1:8082` |
| Milvus WebUI | `http://127.0.0.1:8083/webui` |
| RedisInsight | `http://127.0.0.1:8084` |
| RabbitMQ Management | `http://127.0.0.1:8085` |
| Prometheus | `http://127.0.0.1:8086` |
| Admin dashboard | Open the Dashboard button in the frontend at `http://127.0.0.1:8080` |
| Credentials | Development defaults are templated in `.env.example`; runtime values should live in root `.env` |

The primary frontend and API path now uses backend-issued bearer sessions from `/api/auth/register` and `/api/auth/login`. Meeting, file, chat, and admin calls send:

```text
Authorization: Bearer <session-token>
```

Development header auth is still available as a local fallback when no bearer token is present:

```text
X-User-ID: <uuid>
X-Workspace-ID: <uuid>
```

Optional local bootstrap headers are `X-User-Email`, `X-User-Name`, `X-Workspace-Name`, and `X-User-Role`. This fallback is for local development only; backend bearer-session auth is the product path.

Implemented product roles:

| Role | Permission |
|---|---|
| `Admin` | Access metrics and temporary operational logs, manage accounts, delete meeting sessions, and trigger cascading cleanup |
| `User` | Default role for newly registered accounts; create/upload/process/chat with own meetings and manage own unlinked uploaded files |

The frontend may hide unavailable actions for UX, but backend authorization remains authoritative.

## Explanation Files

- `docs/explanations/backend-explanation.md` - Current FastAPI backend structure and health flow.
- `docs/explanations/frontend-explanation.md` - Current Vite/React frontend structure and meeting workflow.
- `docs/explanations/infrastructure-explanation.md` - Current Docker Compose, gateway, storage, vector DB, and monitoring runtime.
- `docs/explanations/worker-explanation.md` - Current Celery worker/Beat, Redis locks, reconciliation, and processing pipeline behavior.
- `docs/explanations/documentation-explanation.md` - Project documentation rules and layout.

## Open Product Decisions

| Decision | Default Direction | When To Revisit |
|---|---|---|
| Auth | Local register/login, backend bearer sessions, default `User` registration, admin role-management UI, `Admin`/`User` roles, and account-aware frontend UI are implemented | Revisit before SSO, invite-only admin creation, or enterprise identity |
| Recording | Completed recording upload first | When live transcription becomes a priority |
| ASR provider | Local faster-whisper command runner is implemented and verified through MP3 upload processing | Revisit when changing ASR model size, language defaults, or GPU acceleration |
| LLM provider | API/private endpoint first with Ollama fallback; the same LLM boundary is used for analysis JSON and chat answers | Revisit when improving prompts, evaluations, and chat generation |
| Embeddings and rerank | Ollama text embeddings, PostgreSQL chunk records, Milvus REST upsert/query, and local SentenceTransformers rerank are implemented | Revisit model choices after latency and quality evaluation |
| Guardrails | Ollama guardrail provider, transcript/input/context/output checks, safe refusals, and `not_enough_evidence` downgrade are implemented | Revisit after live model latency checks and policy tuning |
| Raw audio retention | Private object storage with explicit future retention policy | Before production or real user data |
| File/session deletion | Direct file deletion is blocked while a meeting session references the file; admin session deletion cascades linked file cleanup | Revisit when adding shared files or reusable uploads |
| Operational log retention | Temporary Redis Stream capped at 1,000 events with a 24-hour sliding TTL | Revisit when centralized durable log aggregation is required |
| Cross-meeting chat | Out of MVP | After single-meeting chat is reliable |

## Phase Summary

| Phase | Name | Status |
|---|---|---|
| 1 | Repository foundation | Done |
| 2 | Local runtime and infrastructure | Done |
| 3 | Meeting upload and core records | Done |
| 4 | Processing pipeline | Done |
| 5 | Retrieval and chat | Done |
| 5.5 | Voice processing and rerank | Done |
| 5.6 | Local guardrails | Done |
| 6 | Admin and operations | Done |
| 7 | Hardening | Done |
| 8 | Operational logs | Done |
| 9 | Full JSON RAG coverage | Done |
| 10 | Frontend and backend resilience | Pending |
