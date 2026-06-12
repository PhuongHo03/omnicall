# Backend Explanation

## Structure

```text
backend/
├── __init__.py                    <- Backend package marker
├── Dockerfile                     <- Backend container image
├── configs/
│   ├── __init__.py
│   ├── celery_app.py              <- Celery application configured with RabbitMQ
│   ├── database.py                <- SQLAlchemy engine/session setup
│   └── settings.py                <- Environment-backed application settings
├── controllers/
│   ├── __init__.py
│   ├── health_controller.py       <- `/api/health` route handler
│   └── meeting_controller.py      <- Meeting, upload, and processing endpoints
├── dependencies/
│   ├── __init__.py
│   └── auth.py                    <- Development auth context dependency
├── dtos/
│   ├── __init__.py
│   ├── error_dto.py               <- Safe error response contract
│   ├── health_dto.py              <- Health response contract
│   └── meeting_dto.py             <- Meeting API request/response contracts
├── migrations/
│   ├── env.py                     <- Alembic environment
│   └── versions/
│       ├── 0001_core_meeting_records.py
│       ├── 0002_meeting_intelligence_results.py
│       ├── 0003_meeting_intelligence_indexes.py
│       ├── 0004_meeting_chunks.py
│       └── 0005_chat_history.py
├── middlewares/
│   ├── __init__.py
│   └── request_id_middleware.py   <- `X-Request-ID` response header middleware
├── models/
│   ├── __init__.py
│   ├── core_models.py             <- User, workspace, membership models
│   ├── enums.py                   <- Meeting and processing status enums
│   └── meeting_models.py          <- Meeting, asset, job, result, transcript segment, insight models
├── providers/
│   ├── __init__.py
│   ├── analysis_provider.py       <- Deterministic processed JSON provider stub
│   ├── embedding_provider.py      <- Deterministic local text embedding fallback
│   ├── llm_provider.py            <- LLM provider adapters and Ollama fallback selection
│   ├── lock_provider.py           <- Redis lock provider for worker idempotency
│   ├── queue_provider.py          <- Celery task publishing adapter
│   ├── storage_provider.py        <- MinIO object storage adapter
│   ├── text_extraction_provider.py <- Text transcript and notes extraction adapter
│   ├── transcript_types.py        <- Shared transcript segment value type
│   ├── transcription_provider.py  <- Deterministic transcript provider stub
│   └── vector_provider.py         <- Milvus REST vector index adapter and PostgreSQL fallback switch
├── repositories/
│   ├── __init__.py
│   ├── auth_repository.py         <- User/workspace/membership persistence
│   ├── chat_repository.py         <- Chat session and message persistence
│   ├── meeting_repository.py      <- Meeting, asset, job, result persistence
│   └── retrieval_repository.py    <- Retrieval chunk persistence
├── services/
│   ├── __init__.py
│   ├── chat_service.py            <- Meeting-grounded chat use case
│   ├── health_service.py          <- Health use case
│   ├── intelligence_service.py    <- Processed JSON read use cases
│   ├── meeting_service.py         <- Meeting upload and processing use cases
│   ├── processing_pipeline_service.py <- Worker processing use case
│   ├── retrieval_index_service.py <- Processed JSON retrieval chunk builder
│   └── retrieval_search_service.py <- Milvus search with PostgreSQL authoritative record reload and fallback ranking
├── tasks/
│   ├── __init__.py
│   └── processing_tasks.py        <- Celery task registration for meeting processing
├── utils/
│   ├── __init__.py
│   └── exceptions.py              <- Shared base application exception
├── main.py                        <- FastAPI app factory and route registration
├── requirements.txt               <- Backend runtime dependencies
└── requirements-dev.txt           <- Backend development/test dependencies
```

The backend currently follows the layered structure:

```text
HTTP request -> middleware -> controller -> service -> DTO response
```

DTOs are separate from SQLAlchemy models. Controllers call services; services coordinate repositories and infrastructure providers.

## Runtime Behavior

`backend/main.py` exposes a FastAPI app through `app = create_app()`.

The app registers:

- `RequestIdMiddleware`, which copies an incoming `X-Request-ID` header or generates a UUID and returns it in the response.
- CORS middleware using `CORS_ORIGINS` from settings.
- `ApplicationError` handler, which returns safe `{code, message}` JSON without internal stack traces.
- The health router under the configured `API_PREFIX`, defaulting to `/api`.
- The meeting router under the configured `API_PREFIX`, defaulting to `/api`.

Current public backend route:

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/health` | `{"app":"Omnicall API","status":"ok"}` |
| `POST` | `/api/meetings` | Created meeting shell |
| `GET` | `/api/meetings` | Meetings visible in the current workspace |
| `GET` | `/api/meetings/{meetingId}` | Meeting detail and status |
| `POST` | `/api/meetings/{meetingId}/assets` | Uploaded audio/video/text asset metadata |
| `POST` | `/api/meetings/{meetingId}/process` | Processing job queued or visible queue failure |
| `GET` | `/api/meetings/{meetingId}/processing-status` | Meeting status plus latest processing job |
| `GET` | `/api/meetings/{meetingId}/transcript` | Transcript, citations, and quality sections from the processed JSON |
| `GET` | `/api/meetings/{meetingId}/insights` | Summary, analysis, citations, and quality sections from the processed JSON |
| `GET` | `/api/meetings/{meetingId}/intelligence-result` | Complete `meeting_intelligence_result` JSON |
| `POST` | `/api/meetings/{meetingId}/chat` | Ask a question grounded in one processed meeting |
| `GET` | `/api/meetings/{meetingId}/chat/{sessionId}` | Reload saved chat messages for one meeting chat session |

In the Compose runtime, the backend is not host-published directly. NGINX proxies public `/api/` traffic to `backend:8000` over the internal Docker network.

## Auth Boundary

Meeting APIs currently use a development header-based auth context:

```text
X-User-ID: <uuid>
X-Workspace-ID: <uuid>
```

Optional bootstrap headers:

```text
X-User-Email
X-User-Name
X-Workspace-Name
```

`backend/dependencies/auth.py` validates UUID header values, creates local `users`, `workspaces`, and `workspace_members` records if they do not exist, and returns a `CurrentUserContext`. This is a development boundary, not production authentication.

All meeting reads, uploads, and process triggers are scoped by `workspace_id`.

## Persistence

Alembic migration `0001_core_meeting_records` creates:

| Table | Purpose |
|---|---|
| `users` | Local user identity records |
| `workspaces` | Workspace boundary |
| `workspace_members` | User membership and role |
| `meetings` | Main meeting aggregate and status |
| `meeting_assets` | MinIO object metadata |
| `processing_jobs` | Async processing state and idempotency |

Alembic migration `0002_intel_results` creates:

| Table | Purpose |
|---|---|
| `meeting_intelligence_results` | Versioned processed transcript JSON stored as PostgreSQL JSONB |

Alembic migration `0003_intel_indexes` creates derived indexes:

| Table | Purpose |
|---|---|
| `transcript_segments` | Rebuildable transcript segment rows derived from `meeting_intelligence_results.result_json` |
| `meeting_insights` | Rebuildable structured insight rows derived from summary and analysis JSON sections |

Alembic migration `0004_meeting_chunks` creates retrieval chunk indexes:

| Table | Purpose |
|---|---|
| `meeting_chunks` | Rebuildable retrieval chunks derived from processed JSON sections and transcript fallback entries |

Alembic migration `0005_chat_history` creates chat history records:

| Table | Purpose |
|---|---|
| `chat_sessions` | Durable user chat sessions scoped to one meeting and workspace |
| `chat_messages` | Saved user/assistant messages, retrieved chunk IDs, citations, evidence metadata, and timestamps |

Important constraints:

| Constraint | Purpose |
|---|---|
| `uq_workspace_members_workspace_user` | One membership per user/workspace |
| `uq_meeting_assets_object_key` | Object key cannot point to multiple assets |
| `uq_meeting_assets_meeting_idempotency` | Retry-safe upload metadata |
| `uq_processing_jobs_meeting_idempotency` | Retry-safe processing trigger |
| `uq_meeting_intelligence_result_version` | One persisted result per meeting and schema version |
| `uq_transcript_segments_meeting_segment` | One derived segment row per meeting segment ID |
| `uq_meeting_insights_meeting_section_item` | One derived insight row per meeting section item |
| `uq_meeting_chunks_meeting_chunk` | One derived retrieval chunk per meeting chunk ID |

Meeting statuses are `DRAFT`, `UPLOADED`, `QUEUED`, `PROCESSING`, `READY`, and `FAILED`.

Processing job statuses are `PENDING`, `RUNNING`, `RETRYING`, `SUCCEEDED`, `FAILED`, and `CANCELLED`.

## Upload And Queue Flow

Upload flow:

```text
HTTP multipart upload
-> auth context
-> meeting workspace check
-> extension/content-type/size/state validation
-> MinIO put_object
-> meeting_assets row
-> meeting status UPLOADED
```

Process flow:

```text
POST /process
-> auth context
-> meeting workspace check
-> asset existence check
-> processing_jobs row
-> meeting status QUEUED
-> DB commit
-> Celery send_task to RabbitMQ
```

If queue publishing fails after the job commit, the backend marks the job and meeting as `FAILED` with a user-safe failure reason and stores the internal error only in the database.

## Processing Result Read Flow

The worker writes a complete processed result document to `meeting_intelligence_results.result_json` after a successful processing run. The current schema version is:

```text
meeting-intelligence-result.v1
```

The persisted JSON contains:

- `meeting`, `source`, `participants`, `transcript`, `summary`, `analysis`, `citations`, and `quality`.
- Transcript segments inside `transcript.segments`.
- Structured analysis sections such as topics, decisions, action items, important notes, timeline, risks, blockers, dependencies, open questions, follow-ups, outcomes, requirements, constraints, assumptions, conflicts, metrics, parking lot, entities, glossary, and explicit empty-section reasons.

Read endpoints do not call model providers. They load the authorized meeting, read the latest persisted result, and return either the full JSON or a view of relevant sections. Provider prompts and raw provider responses are not exposed.

Current provider behavior is intentionally deterministic:

| Provider | Current adapter | Purpose |
|---|---|---|
| Transcription | `LocalTranscriptionProvider` | Produces one placeholder transcript segment to validate the processing contract |
| Text extraction | `DocumentTextExtractionProvider` | Reads `.txt`, `.md`, `.vtt`, and `.srt` uploads from MinIO and turns timestamp/speaker lines into transcript segments |
| Analysis | `LocalAnalysisProvider` | Produces a complete `meeting-intelligence-result.v1` JSON with warnings that real ASR/LLM providers are not connected |
| Analysis | `LLMAnalysisProvider` | When `ANALYSIS_PROVIDER=llm`, calls the configured LLM provider, merges generated intelligence sections into the canonical result shape, preserves the ASR transcript, and falls back to local analysis on provider failure |
| LLM | `OpenAICompatibleLLMProvider`, `CustomJSONEndpointLLMProvider`, `OllamaLLMProvider`, `FallbackLLMProvider` | Selects API/private endpoint/Ollama providers and parses JSON responses for future LLM-backed analysis |
| Text embedding | `LocalHashEmbeddingProvider` | Deterministic local fallback that embeds retrieval chunks for MVP indexing and tests |
| Vector index | `MilvusVectorProvider`, `NoopVectorProvider` | Upserts derived chunk vectors to Milvus through REST and falls back to PostgreSQL ranking when vector search is unavailable |

Local Compose defaults to `ANALYSIS_PROVIDER=local` so development does not require a running LLM. Setting `ANALYSIS_PROVIDER=llm` enables LLM-backed result generation with deterministic fallback. Text transcript uploads can already produce transcript segments without ASR. Production-quality audio ASR, diarization, prompt evaluation, embedding, and rerank adapters continue in later provider hardening and retrieval work.

After each successful processing run, the worker persists the full JSONB result and then rebuilds `transcript_segments`, `meeting_insights`, and `meeting_chunks`. These rows are derived lookup/index records for retrieval, filtering, and citations; the JSONB result remains the authoritative product artifact.

Retrieval chunks are built from structured processed JSON sections first, including summary, detailed summary, key points, decisions, action items, important notes, timeline, risks, blockers, dependencies, follow-ups, open questions, topics, entities, and important quotes when present. Transcript segment chunks are also created as fallback evidence. Low-signal chunk text is skipped for retrieval indexing, but the original transcript remains preserved inside `meeting_intelligence_results.result_json`.

When `VECTOR_PROVIDER=milvus`, `RetrievalIndexService` also upserts derived vectors to the Milvus REST API after `meeting_chunks` are persisted. The upsert payload includes stable derived references: workspace ID, meeting ID, result ID, chunk ID, JSON pointer, source type, section type, and time range. Milvus failures are recorded in job `retrievalMetadata.vectorIndex` and do not fail the meeting because Milvus is derived infrastructure.

## Meeting Chat Flow

Chat is scoped to a single `READY` meeting. The backend checks the workspace/meeting boundary before reading chunks or chat history.

Question flow:

```text
POST /api/meetings/{meetingId}/chat
-> auth context
-> meeting workspace and READY-state check
-> create or load chat_session
-> save user chat_message
-> embed question with local text embedding fallback
-> vector search in Milvus when available
-> reload authoritative meeting_chunks from PostgreSQL
-> PostgreSQL fallback ranking if Milvus is unavailable or empty
-> call LLMProvider with retrieved context
-> fallback to local retrieval summary if the provider fails
-> save assistant chat_message with retrieved chunk IDs and citations
-> return answer, evidence state, and source citations
```

Retrieval search prefers Milvus when available, then reloads the returned `chunk_id` values from PostgreSQL within the authorized workspace and meeting. If Milvus is unavailable, empty, or returns an error, the service falls back to PostgreSQL ranking over persisted `meeting_chunks`, combining lexical overlap, deterministic local embedding similarity, and structured-section priority. PostgreSQL records are always the authoritative chunks returned to chat.

Because the MVP local hash embedding is deterministic but not semantically rich, retrieved chunks are also revalidated against meaningful query-token overlap before being used as evidence. This guard applies to both Milvus hits and PostgreSQL fallback ranking when local hash embeddings are active, so unrelated vector neighbors do not become cited answer context.

If no chunks meet the evidence threshold, chat returns a `not_enough_evidence` answer and saves it without citations. Provider prompts and raw provider responses are not saved in chat history.

## Configuration

Settings are loaded by `backend/configs/settings.py` using `pydantic-settings`.

| Env var | Default | Purpose |
|---|---|---|
| `APP_NAME` | `Omnicall API` | FastAPI app title and health response app name |
| `APP_ENV` | `local` | Runtime environment label |
| `API_PREFIX` | `/api` | Backend API route prefix |
| `CORS_ORIGINS` | empty list | Allowed browser origins |
| `POSTGRES_*` | local Compose values | PostgreSQL connection settings |
| `RABBITMQ_*` | local Compose values | Celery broker connection settings |
| `REDIS_*` | local Compose values | Redis connection and processing lock TTL |
| `MINIO_*` | local Compose values | Object storage settings |
| `UPLOAD_MAX_BYTES` | `524288000` | Backend upload size limit |
| `UPLOAD_ALLOWED_EXTENSIONS` | audio/video/text transcript extensions | Upload extension allowlist |
| `UPLOAD_ALLOWED_CONTENT_TYPES` | audio/video/text transcript MIME types | Upload content-type allowlist |
| `ASR_PROVIDER` | `local` | ASR provider selection placeholder |
| `SPEAKER_EMBEDDING_PROVIDER` | `wespeaker` | Speaker embedding/diarization provider selection placeholder |
| `ANALYSIS_PROVIDER` | `local` | Analysis path: `local` deterministic or `llm` with deterministic fallback |
| `TEXT_EMBEDDING_PROVIDER` | `local` | Text embedding provider selection placeholder |
| `EMBEDDING_DIMENSIONS` | `64` | Local text embedding vector size for deterministic retrieval chunk indexing |
| `RERANK_PROVIDER` | `local` | Rerank provider selection placeholder |
| `VECTOR_PROVIDER` | `milvus` | Vector index provider: `milvus` or fallback-only mode |
| `MILVUS_HOST` | `milvus` | Milvus REST host used by backend and worker |
| `MILVUS_PORT` | `19530` | Milvus REST port |
| `MILVUS_COLLECTION` | `meeting_chunks` | Milvus collection for derived meeting chunk vectors |
| `LLM_PROVIDER` | `endpoint` | Primary LLM provider: `api`, `endpoint`, or `ollama` |
| `LLM_API_BASE_URL` | `http://localhost:8001/v1` | External API/private endpoint base URL |
| `LLM_API_KEY` | empty | Provider credential, passed only to backend/worker containers |
| `LLM_MODEL` | empty | External API/private endpoint model name |
| `LLM_ENDPOINT_COMPATIBILITY` | `openai` | HTTP endpoint mode: `openai` or `custom-json` |
| `LLM_TIMEOUT_SECONDS` | `60` | Provider request timeout |
| `LLM_MAX_RETRIES` | `1` | Retry count for retryable provider HTTP failures |
| `LLM_RETRY_BACKOFF_SECONDS` | `0.2` | Linear backoff base between provider retries |
| `LLM_FALLBACK_PROVIDER` | `ollama` | Fallback provider after API/endpoint failures |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Host Ollama service URL from containers |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Local fallback model |

The settings loader reads a root `.env` file when present.

## Dependencies

`backend/requirements.txt` currently contains:

- `fastapi`
- `alembic`
- `celery`
- `minio`
- `psycopg[binary]`
- `pydantic-settings`
- `python-multipart`
- `redis`
- `SQLAlchemy`
- `uvicorn[standard]`

`backend/requirements-dev.txt` adds:

- `httpx` for FastAPI/Starlette TestClient checks.
- `pytest` for richer backend test workflows when dev dependencies are available.

## Local Commands

Compile syntax without installing dependencies:

```bash
python3 -m compileall backend
```

Run after dependencies are installed:

```bash
uvicorn backend.main:app --reload
```

Run through Docker Compose:

```bash
docker compose --env-file .env.example up -d --build backend worker nginx
curl http://127.0.0.1:8080/api/health
```

Run migrations:

```bash
docker compose --env-file .env.example exec -T backend alembic upgrade head
```

Run backend tests in the backend container:

```bash
docker compose --env-file .env.example exec -T backend python -m unittest discover -s backend/tests -v
```

Create and process a meeting through the gateway:

```bash
curl -X POST http://127.0.0.1:8080/api/meetings \
  -H "X-User-ID: 11111111-1111-4111-8111-111111111111" \
  -H "X-Workspace-ID: 22222222-2222-4222-8222-222222222222" \
  -H "Content-Type: application/json" \
  -d '{"title":"Example meeting","language":"vi"}'
```

Read the processed result after the meeting reaches `READY`:

```bash
curl http://127.0.0.1:8080/api/meetings/<meeting-id>/intelligence-result \
  -H "X-User-ID: 11111111-1111-4111-8111-111111111111" \
  -H "X-Workspace-ID: 22222222-2222-4222-8222-222222222222"
```

Test import and health response with temporary dependencies:

```bash
python3 -m pip install --target /tmp/omnicall-backend-deps -r backend/requirements-dev.txt
PYTHONPATH=/tmp/omnicall-backend-deps:. python3 - <<'PY'
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
response = client.get("/api/health")
assert response.status_code == 200
assert response.json() == {"app": "Omnicall API", "status": "ok"}
PY
```

Live HTTP verification command used in Phase 1:

```bash
PYTHONPATH=/tmp/omnicall-backend-deps:. python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
curl -s -i http://127.0.0.1:8000/api/health
```

The live response returned `200 OK`, `{"app":"Omnicall API","status":"ok"}`, and an `X-Request-ID` header.

*Document reflects project state at **Phase 5 - Retrieval And Chat** complete. Backend compile, Compose config, Alembic migration at `0005_chat_history`, gateway health, processed JSON read APIs, derived transcript/insight/chunk indexes, local text embedding fallback, Milvus REST vector upsert/search with PostgreSQL revalidation, meeting chat APIs, chat persistence, source citations, evidence guard tests, LLM provider and LLM analysis tests, worker idempotency/failure tests, retrieval tests, manual gateway chat smoke, and backend `unittest` suite with 30 tests passed.*
