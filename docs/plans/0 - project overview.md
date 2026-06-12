# Project Overview

## Tech Stack

- Frontend: React, TypeScript, Vite.
- Backend API: Python, FastAPI.
- Worker: Python worker process, Celery, RabbitMQ.
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
| Upload meeting | Add an existing audio/video file, transcript, or meeting notes file | Private object is stored, metadata is saved, processing job is queued |
| Record meeting | Capture a live meeting from the browser | Recording is uploaded as an asset and enters the same processing pipeline |
| Review analysis | Understand what happened without replaying the whole meeting | Complete processed transcript result is displayed |
| Ask meeting chat | Retrieve precise information from the processed result | Frontend chat tab asks the backend, which answers from processed intelligence first and cites transcript evidence |
| Monitor operations | See system health and processing state | Admin dashboard reads normalized backend metrics |

Out of MVP unless explicitly pulled forward:

- Cross-meeting workspace chat.
- Real-time partial transcription.
- External task-tool sync.
- Advanced speaker diarization correction UI.
- Automated retention/deletion policy enforcement.
- SSO and enterprise policy management.

## Core Domain Concepts

Durable business state belongs in PostgreSQL.

| Concept | Purpose |
|---|---|
| `workspace` | Collaboration and permission boundary |
| `user` | Account identity |
| `workspace_member` | Role and membership inside a workspace |
| `meeting` | Main aggregate for uploaded/recorded meeting content |
| `meeting_asset` | File metadata for raw uploads, recordings, transcripts, and exports stored in MinIO |
| `processing_job` | Async job state for transcription, analysis, and embedding work |
| `meeting_intelligence_result` | Versioned processed transcript JSON used as the main knowledge base for chat |
| `transcript_segment` | Derived transcript segment rows rebuilt from the processed JSON |
| `meeting_insight` | Derived normalized/indexed view of structured items inside the processed JSON |
| `meeting_chunk` | Retrieval unit derived from processed JSON sections and source ranges |
| `chat_session` | User conversation scoped to a meeting |
| `chat_message` | Saved user questions, assistant answers, citations, and timestamps |
| `audit_event` | Security and operational trace for important actions |

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

## Meeting Intelligence Pipeline

Core asynchronous pipeline:

```text
upload/recording
-> backend validation
-> MinIO object
-> PostgreSQL asset + processing_job
-> RabbitMQ task
-> worker lock + idempotency check
-> transcription
-> processed transcript JSON generation
-> schema validation, quality checks, and source linking
-> JSON-section chunking
-> embedding generation
-> PostgreSQL retrieval chunk persistence
-> Milvus vector upsert
-> PostgreSQL status update
```

The current Phase 5 backend slice persists retrieval chunks and deterministic local embeddings in PostgreSQL first, then upserts derived vectors into Milvus. PostgreSQL chunk records stay authoritative and are reloaded after vector search.

Chat retrieval flow:

```text
question
-> backend permission check
-> query normalization
-> query embedding
-> vector search in Milvus
-> load authoritative processed JSON sections/chunks
-> evidence guard against irrelevant local-embedding hits
-> load source evidence from transcript entries inside the JSON
-> answer generation with cited context
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
    "language": "vi",
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

Implemented provider configuration keys:

```text
LLM_PROVIDER=api|endpoint|ollama
LLM_API_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL=...
LLM_ENDPOINT_COMPATIBILITY=openai|custom-json
LLM_TIMEOUT_SECONDS=60
LLM_FALLBACK_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=...

ASR_PROVIDER=local|api|endpoint
SPEAKER_EMBEDDING_PROVIDER=wespeaker
ANALYSIS_PROVIDER=local|llm
TEXT_EMBEDDING_PROVIDER=local|api|endpoint
EMBEDDING_DIMENSIONS=64
VECTOR_PROVIDER=milvus
MILVUS_HOST=milvus
MILVUS_PORT=19530
MILVUS_COLLECTION=meeting_chunks
RERANK_PROVIDER=local|api|endpoint
```

## MVP API Surface

Backend endpoints:

| Method | Path | Status | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | Implemented | Read backend health |
| `POST` | `/api/auth/login` | Planned | Start authenticated session |
| `POST` | `/api/auth/logout` | Planned | End session |
| `GET` | `/api/me` | Planned | Read current user/session context |
| `POST` | `/api/meetings` | Implemented | Create a meeting shell |
| `GET` | `/api/meetings` | Implemented | List meetings visible to the user |
| `GET` | `/api/meetings/{meetingId}` | Implemented | Read meeting detail and status |
| `POST` | `/api/meetings/{meetingId}/assets` | Implemented | Upload meeting file/recording asset, transcript, or notes text |
| `POST` | `/api/meetings/{meetingId}/process` | Implemented | Queue processing |
| `GET` | `/api/meetings/{meetingId}/processing-status` | Implemented | Read meeting/job progress |
| `GET` | `/api/meetings/{meetingId}/transcript` | Implemented | Read transcript segments from the processed JSON |
| `GET` | `/api/meetings/{meetingId}/insights` | Implemented | Read structured analysis from the processed JSON |
| `GET` | `/api/meetings/{meetingId}/intelligence-result` | Implemented | Read the complete processed transcript JSON when needed |
| `POST` | `/api/meetings/{meetingId}/chat` | Implemented | Ask a meeting-grounded question |
| `GET` | `/api/meetings/{meetingId}/chat/{sessionId}` | Implemented | Read chat history |
| `GET` | `/api/admin/metrics` | Planned | Read normalized admin metrics through backend auth |

Frontend may validate input shape for UX, but backend must revalidate all uploads, permissions, and state transitions.

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
│   │   ├── layouts/                  <- App shell
│   │   ├── components/               <- Shared UI components
│   │   ├── styles/                   <- Global CSS
│   │   └── features/meetings/        <- Meeting feature layers
│   └── package.json                  <- Frontend dependencies and scripts
├── infras/                           <- Infrastructure service config
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
  - Keep root-level frontend folders only for shared code: `components`, `layouts`, `styles`, `utils`, and `assets`.
  - Add feature layers such as `api`, `dtos`, `hooks`, `screens`, `states`, `types`, and `components` only when they have real responsibility.
  - Keep routes thin, screens compositional, API calls in `api`, runtime validation/mapping in `dtos`, orchestration in `hooks`, reusable state transitions in `states`, and feature-only UI in feature `components`.

## Connection & Runtime Info

| Resource | Detail |
|---|---|
| Gateway health | `GET http://127.0.0.1:8080/health` through NGINX |
| Frontend app | `GET http://127.0.0.1:8080/` through NGINX |
| Backend health through gateway | `GET http://127.0.0.1:8080/api/health` |
| Local backend command | `uvicorn backend.main:app --reload` |
| Local Compose command | `docker compose --env-file .env.example up -d --build` |
| Migration command | `docker compose --env-file .env.example exec -T backend alembic upgrade head` |
| Worker command | `celery -A backend.configs.celery_app.celery_app worker --queues=meeting-processing` |
| Env template | Root `.env.example` |
| Public URL | `http://127.0.0.1:8080` locally when `APP_BIND_IP=0.0.0.0` and `NGINX_PORT=8080` |
| Adminer | `http://127.0.0.1:8081` |
| RedisInsight | `http://127.0.0.1:5540` |
| RabbitMQ Management | `http://127.0.0.1:15672` |
| MinIO Console | `http://127.0.0.1:9001` |
| Prometheus | `http://127.0.0.1:9096` |
| Credentials | Development defaults are in `.env.example`; replace before any shared environment |

Implemented meeting APIs currently use a development auth context:

```text
X-User-ID: <uuid>
X-Workspace-ID: <uuid>
```

Optional local bootstrap headers are `X-User-Email`, `X-User-Name`, and `X-Workspace-Name`. Production authentication remains planned.

## Explanation Files

- `docs/explanations/backend-explanation.md` - Current FastAPI backend structure and health flow.
- `docs/explanations/frontend-explanation.md` - Current Vite/React frontend structure and meeting workflow.
- `docs/explanations/infrastructure-explanation.md` - Current Docker Compose, gateway, storage, vector DB, and monitoring runtime.
- `docs/explanations/worker-explanation.md` - Current Celery worker, Redis lock, and processing pipeline behavior.
- `docs/explanations/documentation-explanation.md` - Project documentation rules and layout.

## Open Product Decisions

| Decision | Default Direction | When To Revisit |
|---|---|---|
| Auth | Development header context now; email/password or simple local accounts for MVP later | Before multi-tenant production use |
| Recording | Completed recording upload first | When live transcription becomes a priority |
| ASR provider | Deterministic local placeholder now; concrete adapter during Phase 4 | Before production-quality processing |
| LLM provider | Provider boundary and `ANALYSIS_PROVIDER=llm` path implemented: API/private endpoint first, Ollama local fallback, deterministic analysis fallback | Revisit when improving prompts, evaluations, and chat generation |
| Embeddings | Local deterministic text embedding fallback, PostgreSQL chunk records, and Milvus REST upsert/query are implemented | When replacing the MVP embedding fallback with production embeddings and reranking |
| Raw audio retention | Private object storage with explicit future retention policy | Before production or real user data |
| Cross-meeting chat | Out of MVP | After single-meeting chat is reliable |

## Phase Summary

| Phase | Name | Status |
|---|---|---|
| 1 | Repository foundation | Done |
| 2 | Local runtime and infrastructure | Done |
| 3 | Meeting upload and core records | Done |
| 4 | Processing pipeline | Done |
| 5 | Retrieval and chat | Done |
| 6 | Admin and operations | Pending |
| 7 | Hardening | Pending |
