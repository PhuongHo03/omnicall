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
│   ├── admin_controller.py        <- Admin metrics, account management, and admin deletion route handlers
│   ├── auth_controller.py         <- Local register/login/logout/me route handlers
│   ├── file_controller.py         <- Account file library route handlers
│   ├── health_controller.py       <- `/api/health` route handler
│   ├── metrics_controller.py      <- Internal `/metrics` Prometheus endpoint
│   └── meeting_controller.py      <- Meeting, upload, and processing endpoints
├── dependencies/
│   ├── __init__.py
│   └── auth.py                    <- Bearer-session auth dependency with local development-header fallback
├── dtos/
│   ├── __init__.py
│   ├── error_dto.py               <- Safe error response contract
│   ├── admin_dto.py               <- Admin metrics and account-management response contracts
│   ├── auth_dto.py                <- Auth request/response contracts
│   ├── health_dto.py              <- Health response contract
│   ├── file_dto.py                <- Account file response contracts
│   └── meeting_dto.py             <- Meeting API request/response contracts
├── migrations/
│   ├── env.py                     <- Alembic environment
│   └── versions/
│       └── 0001_initial_schema.py <- Consolidated local-dev baseline schema
├── middlewares/
│   ├── __init__.py
│   ├── concurrency_middleware.py  <- Per-group Redis concurrent request limiter
│   ├── rate_limit_middleware.py   <- Per-group sliding-window rate limiter with headers
│   └── request_id_middleware.py   <- `X-Request-ID` response header middleware
├── model_runners/
│   ├── __init__.py
│   ├── asr.py                     <- faster-whisper CLI runner for local ASR
│   ├── diarization.py             <- WeSpeaker CLI runner for local diarization
│   └── rerank.py                  <- SentenceTransformers cross-encoder CLI runner for local rerank
├── models/
│   ├── __init__.py
│   ├── core_models.py             <- User, session, and audit models
│   ├── enums.py                   <- Meeting and processing status enums
│   └── meeting_models.py          <- Meeting, asset, result, chunk, and chat-message models
├── providers/
│   ├── __init__.py
│   ├── analysis/                  <- Processed JSON provider adapters
│   ├── contracts/                 <- Shared provider protocols and result/config DTOs
│   ├── app_metrics_provider.py    <- Prometheus application metrics registry and middleware
│   ├── cache_provider.py          <- Redis JSON cache adapter
│   ├── embedding_provider.py      <- Ollama text embedding provider
│   ├── llm/                       <- HTTP, Ollama, fallback, factory, and transport adapters
│   ├── lock_provider.py           <- Redis lock provider for worker idempotency
│   ├── operational_log_provider.py <- Temporary bounded Redis Stream adapter
│   ├── prometheus_provider.py     <- Internal Prometheus HTTP query adapter
│   ├── queue_provider.py          <- Celery task publishing adapter
│   ├── circuit_breaker.py         <- Generic circuit breaker with Prometheus metrics
│   ├── rerank_provider.py         <- Local model rerank command boundary
│   ├── storage_provider.py        <- MinIO object storage adapter
│   ├── transcript_types.py        <- Shared transcript segment value type
│   ├── transcription_provider.py  <- Text/voice transcription routing provider
│   ├── vector_provider.py         <- Milvus REST vector index adapter and PostgreSQL fallback switch
│   └── voice/                     <- Local voice preprocessing, VAD, ASR, and diarization adapters
├── repositories/
│   ├── __init__.py
│   ├── auth_repository.py         <- User/session/audit persistence
│   ├── chat_repository.py         <- Meeting-scoped chat message persistence
│   ├── file_repository.py         <- Account file-library persistence backed by standalone meeting_assets rows
│   ├── meeting_repository.py      <- Meeting, asset, and result persistence
│   └── retrieval_repository.py    <- Retrieval chunk persistence
├── services/
│   ├── __init__.py
│   ├── admin_account_service.py   <- Admin-only account role and account deletion use cases
│   ├── admin_meeting_service.py   <- Meeting deletion and cascading cleanup use case for admin/global and owner-scoped flows
│   ├── admin_metrics_service.py   <- Admin metrics aggregation and Redis cache use case
│   ├── agent/                     <- Agentic RAG bounded context
│   │   ├── context_manager.py     <- Agent context accumulation with chunk deduplication and tool call tracking
│   │   ├── context_coordinator.py <- Chunk limits, token budget, tool history, and answer metadata
│   │   ├── agent_loop.py          <- LLM think step and parallel tool execution boundary
│   │   ├── answer_synthesizer.py <- LLM synthesis, local summary, and retrieval fallback
│   │   ├── fast_path.py           <- Fast path handler for common queries without retrieval
│   │   ├── parallel_executor.py   <- Parallel tool execution with timeout and partial-failure handling
│   │   ├── prompt_builder.py      <- Agent and synthesis prompts plus stable retrieval status copy
│   │   ├── response_utils.py      <- Chunk normalization, evidence, confidence, and fallback helpers
│   │   ├── result_models.py       <- Agent response DTOs
│   │   ├── service.py             <- Main Agentic RAG orchestration loop
│   │   ├── token_management.py    <- Token counting, limits, and budget management
│   │   ├── tool_catalog.py        <- Stable Agent tool definitions and parameters
│   │   ├── tool_definitions.py    <- Agent tool contracts and chunk serialization
│   │   ├── tool_executor.py       <- Retrieval and synthesis tool implementations
│   │   └── tool_registry.py       <- Tool lookup, schema formatting, and dispatch
│   ├── auth_service.py            <- Registration, login, logout, and current account use cases
│   ├── chat_service.py            <- Meeting-grounded chat use case
│   ├── file_service.py            <- Account file library use cases
│   ├── health_service.py          <- Health use case
│   ├── intelligence_service.py    <- Processed JSON read use cases
│   ├── meeting_service.py         <- Meeting upload and processing use cases
│   ├── operational_log_service.py <- Structured processing/RAG event sanitization, tail, and clear use case
│   ├── processing_pipeline_service.py <- Worker processing use case
│   ├── processing/                <- Processing pipeline stage helpers
│   │   └── analysis_stage.py      <- LLM intelligence analysis stage
│   │   └── observability.py       <- Processing timing and sanitized asset/job log context
│   │   └── voice_events.py        <- ASR, VAD, and diarization operational event emission
│   │   └── persistence_stage.py   <- Processed intelligence result persistence stage
│   │   └── result_validation.py   <- RAG-first result schema and evidence reference validation
│   │   └── retrieval_index_stage.py <- Chunk, embedding, and vector indexing stage
│   │   └── transcription_stage.py <- Voice transcription stage and stage events
│   ├── processing_reconciliation_service.py <- Stale pending-job recovery use case
│   └── retrieval/                <- Chunking, indexing, candidate, and search boundaries
├── tasks/
│   ├── __init__.py
│   ├── maintenance_tasks.py       <- Celery reconciliation task registration
│   └── processing_tasks.py        <- Celery meeting-processing task registration
├── utils/
│   ├── __init__.py
│   ├── exceptions.py              <- Shared base application exception
│   └── security.py                <- Password hashing and session-token helpers
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
- The health, auth, file, admin, and meeting routers under the configured `API_PREFIX`, defaulting to `/api`.
- The internal metrics router at `/metrics` for Prometheus scraping.

Current public backend route:

| Method | Path | Response |
|---|---|---|
| `GET` | `/api/health` | `{"app":"Omnicall API","status":"ok"}` |
| `POST` | `/api/auth/register` | Created local account and bearer session |
| `POST` | `/api/auth/login` | Bearer session for an existing account |
| `POST` | `/api/auth/logout` | Revokes the current bearer session |
| `GET` | `/api/me` | Current account and product role |
| `GET` | `/api/files` | Account-scoped uploaded files |
| `POST` | `/api/files` | Upload an account-scoped file |
| `GET` | `/api/files/{fileId}/content` | Authorized account file bytes for playback/download |
| `DELETE` | `/api/files/{fileId}` | Delete an owned unlinked account file |
| `POST` | `/api/meetings` | Created meeting shell with generated ID as the default title |
| `GET` | `/api/meetings` | Meetings owned by the current account |
| `GET` | `/api/meetings/{meetingId}` | Meeting detail and status |
| `PATCH` | `/api/meetings/{meetingId}` | Rename an owned meeting |
| `DELETE` | `/api/meetings/{meetingId}` | Delete an owned meeting session with cascading cleanup |
| `POST` | `/api/meetings/{meetingId}/assets` | Uploaded audio/video asset metadata; one asset per meeting |
| `GET` | `/api/meetings/{meetingId}/assets/{assetId}/content` | Authorized uploaded asset bytes for browser playback or download |
| `POST` | `/api/meetings/{meetingId}/process` | Processing job queued or visible queue failure |
| `GET` | `/api/meetings/{meetingId}/processing-status` | Meeting status plus latest processing job and latest uploaded asset |
| `GET` | `/api/meetings/{meetingId}/intelligence-result` | Complete `meeting_intelligence_result` JSON |
| `POST` | `/api/meetings/{meetingId}/chat` | Ask a question grounded in one processed meeting |
| `GET` | `/api/meetings/{meetingId}/chat` | Reload the meeting-scoped chat thread; returns an empty message list before the first question |
| `GET` | `/api/admin/metrics` | Admin-only normalized operations metrics, cached in Redis |
| `GET` | `/api/admin/accounts` | Admin-only local account list with role metadata |
| `PATCH` | `/api/admin/accounts/{userId}/role` | Admin-only role update for another account |
| `DELETE` | `/api/admin/accounts/{userId}` | Admin-only account deletion for another account with cascading cleanup |
| `DELETE` | `/api/admin/meetings/{meetingId}` | Admin-only meeting session deletion with cascading cleanup |
| `GET` | `/api/admin/logs` | Admin-only temporary processing/RAG event tail with filters |
| `DELETE` | `/api/admin/logs` | Admin-only clear of the temporary Redis event stream |
| `GET` | `/metrics` | Internal Prometheus scrape endpoint |

In the Compose runtime, the backend is not host-published directly. NGINX proxies public `/api/` traffic to `backend:8000` over the internal Docker network.

## Auth Boundary

The primary product auth path is backend-owned bearer sessions. `POST /api/auth/register` creates a local `users` row, an `account_sessions` row, and an audit event. Public registration does not accept or trust a role field; new accounts are always `User`, and admins promote accounts after registration through the admin account dashboard. `POST /api/auth/login` verifies the PBKDF2-HMAC-SHA256 password hash, creates a new bearer session, and records success/failure audit events. `POST /api/auth/logout` revokes the session token hash.

Authenticated requests send:

```text
Authorization: Bearer <session-token>
```

`backend/dependencies/auth.py` resolves the session token hash from `account_sessions`, checks expiry and revocation, loads the user, and returns `CurrentUserContext(user_id, role)`. Product roles are normalized to exactly `Admin` or `User` from `users.role`; sessions no longer store role snapshots.

Development header-based auth remains available only as a local fallback when no bearer token is present:

```text
X-User-ID: <uuid>
```

Optional bootstrap headers:

```text
X-User-Email
X-User-Name
X-User-Role
```

The fallback validates the user UUID, creates or updates a local `users` row, and returns a `CurrentUserContext`. This is a development boundary, not the frontend product path.

All meeting reads, uploads, process triggers, owned meeting deletion, file-library actions, and chat history reads are scoped by `owner_user_id == context.user_id`.

`DELETE /api/meetings/{meetingId}` is available to authenticated `User` and `Admin` accounts for meetings they own. It uses the production cleanup path: acquire the meeting processing lock, require queued processing jobs to be revoked successfully, remove derived vectors, delete worker-derived rows and objects, invalidate the admin metrics cache, and release the lock. Queue or vector cleanup failures return retryable `503` errors and preserve the meeting. If processing is actively running and the lock cannot be acquired, it returns `409 meeting_processing_in_progress`. A request for another account's meeting returns `404 meeting_not_found`.

Admin operations APIs use the same current-context dependency plus a backend role check. `GET /api/admin/metrics`, `DELETE /api/admin/meetings/{meetingId}`, account role updates, and account deletion accept only `Admin` and reject `User` with `403 admin_access_required`. Frontend role checks only hide admin portal affordances; backend authorization is authoritative.

`GET /api/admin/accounts` lists local accounts with display name, email, role, creation time, and whether the current admin may change the role. `PATCH /api/admin/accounts/{userId}/role` accepts only `Admin` or `User`, updates `users.role`, records `admin.account.role_update`, and rejects attempts to change the caller's own role with `409 cannot_change_own_role`.

`DELETE /api/admin/accounts/{userId}` deletes another account only. It rejects self-deletion with `409 cannot_delete_own_account`. Before deleting data, it acquires the same Redis processing locks used by workers for every target meeting. If any lock is already held, deletion is blocked with `409 account_meeting_processing_in_progress` so the account cannot be deleted while a worker is mutating its meeting state. When locks are held, it requires queued Celery processing tasks to be revoked successfully before deleting meetings owned by the target account. Queue or vector cleanup failures abort the transaction and preserve the account data. It then removes standalone file-library `meeting_assets` rows and MinIO objects, deletes the user row so sessions and remaining owned rows cascade, invalidates the Redis admin metrics cache, releases the locks, and records `admin.account.delete`.

`DELETE /api/admin/meetings/{meetingId}` uses the same production-grade cleanup path for a single meeting: acquire the meeting processing lock, require queued processing jobs to be revoked successfully, delete worker-derived rows and objects, invalidate the admin metrics cache, and release the lock. If processing is actively running and the lock cannot be acquired, it returns `409 meeting_processing_in_progress`; if queue cleanup fails, it returns `503 processing_queue_unavailable`.

The current local-dev baseline has no `workspaces`, `workspace_members`, `account_files`, `chat_sessions`, `transcript_segments`, or `meeting_insights` tables. `users.role` is the authoritative role field, and meetings are scoped directly by `meetings.owner_user_id`.

## Admin Metrics Flow

Phase 6 adds an operations path that keeps Prometheus internal and does not expose PromQL to the browser:

```text
Prometheus scrape targets
-> backend PrometheusProvider queries Prometheus
-> AdminMetricsService normalizes target and metric groups
-> Redis JsonCacheProvider stores admin:metrics:snapshot for 10 seconds
-> GET /api/admin/metrics returns one dashboard payload
```

The backend application itself exposes `/metrics` internally. `MetricsMiddleware` records HTTP request counts and latency, and the scrape handler also refreshes PostgreSQL-backed domain gauges for meetings, processing jobs, and chat messages.

### Resilience Middleware

The backend includes rate-limiting and concurrency middleware registered in `main.py` after request-ID and metrics middleware:

- `RateLimitMiddleware` – Redis sliding-window rate limiter with per-group quotas (public: 10/min, auth: 20/min, meetings: 60/min, admin: 30/min). Adds `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers to every rate-limited response. Public endpoints (e.g. `POST /api/auth/register`) use IP-based identification; authenticated endpoints use the Authorization header. Fail-open on Redis errors with in-memory fallback.
- `ConcurrencyMiddleware` – Redis INCR/DECR concurrent request limiter with per-group limits (meetings: 5, admin: 3, auth: 3, default: 5). Routes are matched to groups; unmatched routes pass through. Fail-open on Redis errors.
- `CircuitBreaker` – reusable provider in `backend/providers/circuit_breaker.py` with CLOSED/OPEN/HALF_OPEN states, configurable failure threshold and recovery window. Exports Prometheus counters: `omnicall_circuit_open_total`, `omnicall_circuit_reject_total`, `omnicall_circuit_recovery_success_total`, `omnicall_circuit_recovery_failure_total`.
- Task enqueue guard in `MeetingService.queue_processing()` rejects new tasks when the user exceeds `task_limit_per_user` active tasks, and rejects when the specific meeting already has a QUEUED or PROCESSING task.

All thresholds are configurable via environment variables in the `# ─── Resilience ───` section of `.env`.

The normalized admin response includes:

| Category | Examples |
|---|---|
| Targets | Prometheus active-target health and last scrape errors; this is loaded once from the targets API rather than duplicated as an `up` metric group |
| Backend | Request rate and p95 latency |
| Application | Meetings by status and chat messages by role |
| Worker | Processing jobs by status |
| Containers | Docker container CPU cores and memory working set for the `omnicall` Compose project |
| Database/cache/queue/storage/vector/gateway | PostgreSQL connection states/database size, Redis memory/clients, RabbitMQ queued messages/consumers, MinIO usable/used capacity, etcd database size, Milvus request rate/collections/stored rows, and NGINX active connections |

Backend request rate is grouped by HTTP method, normalized path, and response status. Backend p95 latency is grouped by HTTP method and normalized path so separate operations sharing a route pattern remain distinguishable without fragmenting latency histograms by status code.

## Admin Operational Logs

Operational logs are separate from durable `audit_events`. `OperationalLogService` emits sanitized `info` or `error` events to a capped Redis Stream. It never writes these high-volume events to PostgreSQL and fails open if Redis is temporarily unavailable.

```text
meeting API / worker / RAG service
-> OperationalLogService
-> Redis Stream admin:logs:operational
-> GET /api/admin/logs
-> /admin/logs
```

Processing events cover file upload, queue delivery, worker receive/lock, transcription, audio preprocessing, VAD, ASR, diarization, LLM analysis, validation, persistence, embedding, Milvus upsert, and final result/failure. RAG events cover question receipt, guardrails, query embedding, retrieval source and chunk counts, rerank, LLM answer/fallback, and answer persistence.

Events include meeting/session name and IDs, uploaded file metadata, job/chat IDs, provider/model, duration, counts, and safe error type/message when available. Full prompts, raw transcripts, API keys, passwords, bearer tokens, and secrets are redacted. Primary LLM endpoint failure and the effective Ollama fallback are emitted as separate error/success events.

The LLM analysis start event reports the configured primary model so the log does not look like two models are running at once. The completion event and persisted `source.analysisModel` report the effective model that actually generated the processed JSON. If the primary endpoint fails, a separate `analysis_llm_primary` error event records the primary provider/model and the later analysis completion records the fallback provider/model.

The transcription start event reports the voice routing boundary before ASR begins. Audio/video uploads then report the effective ASR provider/model and include the voice preprocessing, VAD, and diarization provider details in event metadata. Meeting asset uploads are intentionally voice-only; text transcript and notes files are rejected by the meeting upload allowlist instead of entering processing.

## Persistence

Alembic migration `0001_initial_schema` is the consolidated local-dev baseline. It creates 8 business tables plus Alembic's own `alembic_version` table.

| Table | Purpose |
|---|---|
| `users` | Local account identity, password hash, display name, and authoritative `Admin`/`User` role |
| `account_sessions` | Hashed bearer sessions with expiry and revocation |
| `audit_events` | Durable security/audit trail for auth, file, metrics, upload, and deletion flows |
| `meetings` | Main meeting aggregate, owner, title, status, and safe failure reason |
| `meeting_assets` | MinIO object metadata for both meeting-linked uploads and standalone account file-library uploads |
| `meeting_intelligence_results` | Versioned processed transcript JSON stored as PostgreSQL JSONB; this is the authoritative product artifact |
| `meeting_chunks` | Rebuildable retrieval chunks derived from processed JSON sections and transcript fallback entries |
| `chat_messages` | Saved user/assistant messages, retrieved chunk IDs, citations, evidence metadata, and timestamps for one meeting thread |

Removed tables from the earlier local design:

| Removed Table | Replacement |
|---|---|
| `workspaces`, `workspace_members` | `users.role` and direct `meetings.owner_user_id` ownership; retrieval is scoped by `meeting_id` |
| `account_files` | Standalone file-library rows in `meeting_assets` with `meeting_id = NULL` |
| `transcript_segments`, `meeting_insights` | Full transcript and structured insights remain inside `meeting_intelligence_results.result_json`; retrieval indexes use `meeting_chunks` |
| `chat_sessions` | One meeting equals one chat thread; messages are stored directly in `chat_messages.meeting_id` |

Important constraints:

| Constraint | Purpose |
|---|---|
| `uq_meeting_assets_object_key` | Object key cannot point to multiple assets |
| `uq_meeting_assets_meeting_idempotency` | Retry-safe upload metadata |
| `uq_meeting_intelligence_result_version` | One persisted result per meeting and schema version |
| `uq_meeting_chunks_meeting_chunk` | One derived retrieval chunk per meeting chunk ID |

Meeting statuses are `DRAFT`, `UPLOADED`, `QUEUED`, `PROCESSING`, `READY`, and `FAILED`.

Celery Beat periodically invokes the backend-owned reconciliation use case. It selects stale meetings whose authoritative state remains `QUEUED`, republishes the meeting ID through the queue provider, and leaves `FAILED` meetings for an explicit user retry decision.

Processing exception handling rolls back a failed SQLAlchemy transaction before reloading the authoritative meeting row and persisting the safe failure state. Concurrently deleted meetings return `missing`, avoiding secondary `PendingRollbackError` failures.

## Upload And Queue Flow

Upload flow:

```text
HTTP multipart upload
-> auth context
-> meeting owner check
-> one-asset-per-meeting check
-> extension/content-type/size/state validation
-> MinIO put_object
-> meeting_assets row
-> meeting status UPLOADED
```

Upload idempotency is preserved for retries with the same `Idempotency-Key`: the backend returns the existing asset row. A different upload request for a meeting that already has an asset returns `409 meeting_already_has_asset`. This enforces the current product rule that one meeting maps to one uploaded or recorded file and one analysis lineage; users create a new meeting for a different file.

Uploaded asset content is read back through `GET /api/meetings/{meetingId}/assets/{assetId}/content`. The endpoint first checks the meeting against the caller account owner, then loads the object bytes through `ObjectStorageProvider`. It returns the stored content type and an inline content-disposition header so the frontend can create an authenticated Blob URL for audio playback without exposing MinIO directly.

Account file uploads use `POST /api/files`. They store private MinIO objects under `users/{userId}/files/...` and persist standalone `meeting_assets` metadata with `owner_user_id` and `meeting_id = NULL`. `GET /api/files/{fileId}/content` checks owner authorization before returning bytes. `DELETE /api/files/{fileId}` deletes object bytes and metadata only when the file is not linked to an existing meeting session. Meeting-linked assets have `meeting_id` set and return `409 file_linked_to_meeting`; the cleanup path is admin meeting-session deletion.

Process flow:

```text
POST /process
-> auth context
-> meeting owner check
-> asset existence check
-> meeting status QUEUED
-> increment processing attempts
-> DB commit
-> Celery send_task to RabbitMQ
```

If queue publishing fails after the database commit, the backend marks the meeting as `FAILED` with a user-safe failure reason and stores the internal error only in server-side logs.

## Meeting Session Deletion Flow

`DELETE /api/admin/meetings/{meetingId}` is implemented in `AdminMeetingService` and requires an `Admin` context.

The use case loads the meeting by ID, collects all related object keys, and first requires the vector provider to remove derived Milvus vectors for the meeting. Only after vector cleanup succeeds does it delete chat messages, retrieval chunks, processed JSON, meeting asset metadata, and the meeting row, then remove object bytes from MinIO. A vector cleanup failure returns `503 vector_index_unavailable`, leaves PostgreSQL meeting data intact, and allows a later retry instead of silently creating orphan vectors.

The endpoint is safe to retry: a missing meeting returns a successful `{deleted: true}` response for the requested ID, and object deletion ignores missing-object responses.

## Processing Result Read Flow

The worker writes a complete processed result document to `meeting_intelligence_results.result_json` after a successful processing run. The current schema version is:

```text
meeting-intelligence-result.v2
```

The persisted JSON contains:

- `meeting`, `source`, `transcript`, `evidence`, `knowledge`, `summaries`, `quality`, and `extraction`; all extracted intelligence records live under `knowledge.records`.
- Transcript segments inside `transcript.segments`; each segment keeps stable IDs, speaker labels, time ranges, text, and confidence.
- Canonical transcript, structured, derived, and source evidence inside `evidence.items`; transcript items retain deterministic quotes and playback ranges.
- Deterministic speaker profiles and speaker counts inside `knowledge.records` as `participant.speaker_profile` and `fact.speaker_count` records.
- Verified knowledge records for precise RAG: participant profiles, atomic facts, event timeline records, entities, relationship edges, actions, decisions, risks, open questions, hierarchical topics, and executive/topic/timeline summaries.

Read endpoints do not call model providers. They load the authorized meeting, read the latest persisted result, and return either the full JSON or a view of relevant sections. Provider prompts and raw provider responses are not exposed.

Current provider behavior is model-backed for the six model points. Test-only fakes live under `backend/tests/` and are not production fallbacks.

| Provider | Current adapter | Purpose |
|---|---|---|
| Transcription | `LocalTranscriptionProvider` | Routes meeting assets through voice preprocessing/VAD/ASR/diarization; voice failures raise safe processing errors instead of creating placeholder transcript text |
| Voice preprocessing | `LocalAudioPreprocessor` | Reads the original asset bytes from MinIO, normalizes supported media to a stable per-asset temporary 16 kHz mono WAV with ffmpeg, deletes raw temp input, reuses valid derived WAVs across retries, and records duration, sample rate, channel count, and warnings |
| VAD | `LocalVADProvider` | Local energy-based speech-region detector over normalized WAV audio, with configurable minimum speech duration, silence merge gap, energy threshold, and speech-region metadata |
| ASR | `LocalASRProvider` | Runs the repository-owned faster-whisper CPU `int8` runner, parses JSON segments, and maps them into `TranscriptSegment[]` |
| Diarization | `LocalCommandDiarizationProvider` | Runs the repository-owned WeSpeaker CPU runner and merges speaker assignments into transcript segments |
| Analysis | `LLMAnalysisProvider` | Calls the configured LLM provider, retries once with a repair prompt if the provider echoes input or omits required intelligence sections, sends transcript evidence as compact `segmentId|speaker|startMs|endMs|confidence|text` lines, merges LLM candidate knowledge records into the canonical result shape, preserves deterministic transcript/evidence/speaker/source fields, normalizes citation IDs, quarantines malformed or unknown relationship endpoints with quality warnings, supplies a transcript-grounded fallback when the executive summary is empty, and marks unsupported claims when important records lack citations or deterministic sources |
| LLM | `OpenAICompatibleLLMProvider`, `CustomJSONEndpointLLMProvider`, `OllamaLLMProvider`, `FallbackLLMProvider` | Selects API/private endpoint/Ollama providers, tries the configured API/endpoint primary before Ollama fallback, forwards optional per-call JSON temperature, and records the effective provider/model that actually generated the result |
| Text embedding | `OllamaEmbeddingProvider` | Calls local Ollama `/api/embed` with `EMBEDDING_MODEL=nomic-embed-text` and validates the configured vector dimension |
| Vector index | `MilvusVectorProvider`, `NoopVectorProvider` | Upserts derived chunk vectors to Milvus through REST and falls back to PostgreSQL ranking when vector search is unavailable |
| Rerank | `LocalModelRerankProvider` | Runs the repository-owned specialized local reranker and records unavailable metadata when model execution fails |
| Guardrail | `OllamaGuardrailProvider` | Runs local Ollama checks for chat input and assistant output, returning `allowed`/`blocked` metadata with regex pre-check and post-verdict validation |

The six model roles are ASR, speaker diarization/voice embedding, LLM, text embedding, rerank, and guardrail. With the default endpoint-first LLM setup, runtime usually has seven configured model deployments because LLM has both a primary external/private endpoint model and a small Ollama fallback.

## Local Model Runners

The production local model paths are implemented as command runners under `backend/model_runners/` and invoked through provider command templates. This keeps model runtime code behind provider boundaries while letting backend and worker containers share the same image and `model_cache` volume.

| Runner | Command module | Model/runtime | Output contract |
|---|---|---|---|
| ASR | `python -m backend.model_runners.asr` | `faster-whisper` CPU `int8` over the downloaded Whisper snapshot in `/models/asr` | JSON transcript segments with stable IDs, timestamps, text, and confidence |
| Diarization | `python -m backend.model_runners.diarization` | WeSpeaker speaker embedding/diarization over the downloaded snapshot in `/models/diarization` | JSON turns and segment-to-speaker assignments |
| Rerank | `python -m backend.model_runners.rerank` | SentenceTransformers `CrossEncoder` over `/models/rerank` | JSON ranked chunk IDs |

The diarization runner handles the WeSpeaker Hugging Face snapshot shape used by `Wespeaker/wespeaker-voxceleb-resnet34-LM`, including the `avg_model` file alias expected by WeSpeaker. It also uses a WAV loader compatibility patch for CPU containers where the installed `torchaudio` backend cannot decode standard WAV files directly.

Local Compose now includes an `ollama` service. Backend and worker call it through `OLLAMA_BASE_URL=http://ollama:11434`. Meeting processing accepts audio/video assets only; text transcript or notes files are rejected by the meeting upload allowlist. Voice uploads use the default local ASR and diarization command templates in `.env`/`.env.example`, which call the repository-owned model runners above. Phase 5.5 added voice contracts, ffmpeg preprocessing, local energy VAD, local ASR and diarization runners, Ollama text embeddings, and local model rerank. Phase 5.6 added Ollama guardrails around chat input and output. Phase 15 simplified actions to `allowed`/`blocked` and added regex pre-check, few-shot prompt, and post-verdict category validation.

After each successful processing run, the worker persists the full JSONB result and then rebuilds `meeting_chunks`. The full transcript, canonical evidence, speaker stats, fact/entity/event graph, actions, decisions, risks, questions, topics, and summaries stay inside `meeting_intelligence_results.result_json`; the JSONB result remains the authoritative product artifact.

Retrieval chunks are built from the RAG-first JSON knowledge records. `ProcessingPipelineService` delegates persistence to `PersistenceStage` and chunk/embedding/vector work to `RetrievalIndexStage`; `backend/services/retrieval/index_service.py` owns indexing orchestration, `chunk_builder.py` owns section construction, and `chunk_text.py` owns pure formatting/normalization helpers. `RetrievalSearchService` owns query lifecycle and metadata while `candidate_service.py` owns vector/PostgreSQL candidate resolution, intent pinning, and rerank. Candidate retrieval receives a `RetrievalScoring` policy from the orchestration service, so candidate code does not import private helpers back from the search service. Speaker profiles and speaker counts are indexed from `knowledge.records` as participant/fact records; transcript speaker labels remain only in `transcript.segments`. Unified `knowledge.records` use an explicit record-type mapping, including `entity` to `entities`, so entity records are not silently dropped before chunks are built.

The generalized knowledge contract is defined in `backend/services/knowledge/semantic_registry.py` and `contract.py`. The registry owns canonical record families and aliases; an LLM subtype such as `participant_count` remains payload metadata rather than becoming a new top-level schema. Unknown but valid concepts normalize to `observation`, and the v2 record envelope reserves `evidenceRefs`, `sourceRefs`, and `derivedFrom` for provenance. The runtime reducer cutover is tracked in the subsequent migration phase.

Evidence provenance is defined in `backend/services/knowledge/evidence.py`. It models transcript, structured, derived, and source evidence with optional segment/time location, and retrieval resolves evidence through `evidence_items()`/`evidence_by_id()`. The hierarchical reducer emits `evidence.items`; its records reference evidence through `evidenceRefs` and processing windows through `sourceRefs`. `knowledge/normalization.py` is the provider boundary: window-local candidates are mapped to canonical types, subtype payloads, and the observation fallback before persistence.

The agent planner exposes both legacy retrieval sections and generic `recordTypes`/`recordSubtypes` selectors. `search_records` queries indexed chunks by canonical record metadata and optional subtype; specialized tools remain convenience wrappers. The verifier accepts matching record types and payload fields, so a new subtype does not require a new planner branch, tool, or UI component.

Chunk text is contextualized from canonical record fields, including IDs, types, normalized values, owners, statuses, due dates, participant/entity references, confidence, citation IDs, and time ranges. Fact, participant, event, action, decision, risk, and relationship records have higher retrieval priority than broader summaries. Deterministic `participant_count` facts derived from speaker labels receive transcript citation IDs during reduction; the legacy analysis path does the same before persistence, and the indexer also resolves old records through `sourceWindowIds` and the speaker-derived fallback. JSON-only metadata chunks use stable `json-*` citation IDs and their JSON pointer/serialized chunk text as the citation target, without inventing transcript timestamps. Structured-section retrieval preserves the requested section order before the bounded context limit is applied, so high-value facts are not displaced by participant profiles. Transcript windows are still indexed as fallback evidence, but product truth remains the JSON document and low-signal transcript text can be skipped from retrieval without deleting it from `result_json`.

When `VECTOR_PROVIDER=milvus`, `RetrievalIndexService` also upserts derived vectors to the Milvus REST API after `meeting_chunks` are persisted. The upsert payload includes stable derived references: meeting ID, result ID, chunk ID, JSON pointer, source type, section type, time range, and an index generation. Search reloads the authoritative PostgreSQL chunk and rejects vector hits whose generation does not match. Milvus failures are recorded in retrieval metadata and schedule bounded vector repair without making the derived index authoritative.

## Meeting Chat Flow

Chat is scoped to a single `READY` meeting. The public API treats one meeting as one chat thread and does not expose, create, or accept a separate chat-session ID. The backend checks the meeting owner boundary before reading chunks or chat history.

Question flow:

```text
POST /api/meetings/{meetingId}/chat
-> auth context
-> meeting owner and READY-state check
-> guardrail check the user question
-> save user chat_message
-> embed question with local Ollama text embedding model
-> vector search in Milvus when available
-> reload authoritative meeting_chunks from PostgreSQL
-> PostgreSQL fallback ranking if Milvus is unavailable or empty
-> rerank candidates with configured local rerank model command when available
-> call LLMProvider with retrieved context
-> fallback to local retrieval summary if the provider fails
-> guardrail check assistant answer
-> save assistant chat_message with retrieved chunk IDs and verified citations
-> return answer, evidence state, and citation-level evidence
```

Retrieval search prefers Milvus when available, then reloads returned `chunk_id` values from PostgreSQL within the authorized meeting and validates the vector generation. If Milvus is unavailable, empty, returns stale hits, or returns an error, the service falls back to PostgreSQL ranking over persisted `meeting_chunks`. The fallback combines exact lexical overlap, PostgreSQL trigram similarity, and high-priority structured/metadata candidates before rerank. PostgreSQL records are always the authoritative chunks returned to chat. Structured questions are selected through the generic record contract: participant/count questions use participant profiles and participant-count facts; actor/target and location questions use participant, action, entity, event, and fact records plus relation capabilities; timeline questions use temporal fields on event/action/fact records; and all other domains use their canonical record type/subtype and relationship fields. Keyword retrieval first attempts a phrase match, then token-level matching so normalized planner queries such as `price OR cost OR dollar` can find English canonical JSON chunks.

Meeting deletion removes the meeting's operational-log events from Redis after the database deletion commits. Log cleanup is best effort because operational logs are diagnostic data, not the source of truth for meeting deletion. Account deletion applies the same cleanup to every meeting removed with the account, preventing deleted or test-only meetings from remaining as cards in the admin log view.

If no chunks meet the evidence threshold, chat returns a `not_enough_evidence` answer and saves it without citations. Verified citation IDs from answer synthesis are mapped back to authoritative chunks, deduplicated, and persisted separately from retrieved chunk IDs. Retrieval chunk metadata stores `citationQuotes` and `citationLocations` per citation ID; chat response mapping uses the per-citation segment IDs and timestamps instead of the chunk-level aggregate location. Derived JSON records without direct transcript citations receive stable `json-record-*` citation IDs and retain structured provenance; they do not inherit every transcript citation from their source window. Legacy chunk-level citation JSON is normalized when chat history is read. Guardrails now use the simplified `allowed`/`blocked` contract only. If input guardrails block the user question, the service stores a safe assistant refusal without calling the agent. Provider errors fail open as `allowed` with `provider_error` metadata. If output guardrails block an answer, the assistant response is replaced with a safe message and citations are removed. The chat flow no longer expects redacted text, warning actions, or a context guardrail stage. If query embedding fails, retrieval skips Milvus and uses hybrid lexical/trigram/structured PostgreSQL ranking, recording `postgres-fallback-embedding` in search metadata. If a worker exception escapes normal answer generation, it resets `pending_chat_status`, persists one idempotent safe error response keyed by the user message, and publishes an error event. Provider prompts and raw provider responses are not saved in chat history.

Answer prompts live in the Agentic RAG service rather than `MeetingChatService`. Phase 18 removed the unused linear-RAG helper path from `MeetingChatService`, leaving that service focused on permission checks, user/assistant message persistence, guardrail orchestration, agent delegation, SSE status publishing, and operational logs. Assistant message metadata includes agent iterations, tool calls, thoughts, duration, token usage, and guardrail action/categories/provider/model/confidence/latency/promptVersion/textLength/decisionId metadata so answer generation, retrieval ordering, and guardrail decisions can be observed without storing LLM prompts, rerank prompts, guardrail prompts, or raw provider responses. `GET /api/meetings/{meetingId}/chat` returns the authorized meeting thread and messages, allowing the frontend to recover persisted chat after reloads, route changes, or lost browser state.

For local development after changing chunk formats, run `python -m backend.scripts.rebuild_retrieval_index --clear-chat` inside the backend environment to rebuild all PostgreSQL chunks and Milvus vectors from stored `meeting_intelligence_results` and remove chat history that may cite stale chunk IDs. Phase 22 intentionally rejects obsolete pre-RAG-first JSON documents during rebuild; old local meetings must be reprocessed or removed. Use `--meeting-id <id>` to target one meeting. A full disposable reset is still possible with Compose volume deletion, migrations, and reprocessing when old local data is not worth preserving.

The v2 reducer also persists an `identity_resolution` relationship only when the transcript contains explicit self-identification (for example, “this is Andrew”). Being addressed by a name is retained as a participant mention and is not treated as proof of speaker identity. `backend.scripts.verify_v2_cutover` validates v2 status, result presence, relationship endpoints, identity-relationship counts, and orphan retrieval chunks. Runtime reprocessing remains an operational prerequisite: a meeting whose transcription pipeline fails before persistence cannot be reported as migrated until its worker/provider failure is resolved.

## Agentic RAG (Phase 26)

The chat service uses `backend.services.agent.AgenticRAGService` for all chat requests after input guardrails pass. The bounded flow is fast path -> JSON-v2 query plan -> deterministic/parallel retrieval -> evidence verification -> bounded replan -> final synthesis. `query_planner.py` emits canonical `recordTypes`, `recordSubtypes`, and required fields; sections remain only for v2 top-level projections. `search_records` is the generic record boundary and specialized retrieval tools are selector presets over it. `evidence_verifier.py` checks canonical record relevance, payload fields, and evidence refs; `context_coordinator.py` carries record/provenance metadata through token-limited context; and `answer_synthesizer.py` accepts only context-supplied v2 evidence refs before mapping them to UI citations. Runtime defaults are two iterations, one replan, four tool calls per iteration, five chunks per tool, twelve total chunks, 4,000 context tokens, 30 seconds per iteration, and 60 seconds total.

Record searches keep type/subtype selection authoritative: when a planner supplies `recordTypes`, the natural-language question is not required to occur verbatim in the record text. Participant chunks include `recordId` and provenance metadata, so participant and speaker questions resolve through the same generic `search_records` path as every other record type.

Retrieval indexing is v2-only: it requires `schemaVersion=meeting-intelligence-result.v2`, `knowledge.records`, and `evidence.items`. Removed v1 `evidence.citations` data is not silently read. The cutover verifier confirms the current database has three processable v2 meetings, 196 indexed chunks, and no orphan chunks.

The direct analysis adapter uses the explicitly internal `meeting-intelligence-candidate.v2` envelope while extracting window candidates. The hierarchical reducer normalizes those candidates into the only persisted/public contract, `meeting-intelligence-result.v2`; the old v1 result identifier is no longer an active provider constant or fixture.

### Flow

```
user question
-> input guardrail check
-> fast path detection
   -> if fast path: return direct response with evidenceState="fast_path"
-> query planner: intent, record selectors, required fields
-> record/evidence-first retrieval from JSON-v2 PostgreSQL chunks
-> evidence verifier
   -> sufficient: synthesize
   -> missing fields and quota available: replan once and retrieve again
-> AnswerSynthesizer: final answer with verified evidence refs and mapped citations
-> output guardrail check
-> save answer with plan, verification, iteration, replan, and tool metadata
```

LLM JSON generation remains deterministic by default with `temperature=0` for analysis, planning, synthesis, and guardrail-like structured flows. Fast-path detection is the exception: `FastPathHandler` passes `temperature=0.5` for direct greeting, thanks, guidance, and small-talk answers so repeated non-RAG prompts can be less robotic while the response still follows the `{needsRag, answer}` JSON contract.

### Tools

The agent can invoke these retrieval tools:
- `search_semantic`: vector embedding search via Milvus
- `search_keyword`: PostgreSQL phrase-then-token ILIKE search
- `search_records`: generic search by registered v2 record types/subtypes
- `search_section`: limited v2 top-level projection search
- `get_summary`: retrieve the top-level summary projection
- Final synthesis is owned by `AnswerSynthesizer`, outside the tool catalog.

### SSE Events

The agentic flow emits additional SSE events:
- `connected`: initial stream handshake with `{"type":"connected","status":"connected"}`
- `agent_think`: iteration number and message
- `agent_plan`: intent, planned sections, and sub-query count
- `agent_search`: iteration, tool names, and message
- `observation`: iteration, new chunks found, success/failure counts
- `agent_verify`: evidence sufficiency, missing fields, and evidence count
- `agent_replan`: bounded replan number, reason, and missing fields
- `agent_synthesize`: iteration and whether forced
- `fast_path`: for immediate responses

### Agent Metadata

Assistant chat messages include additional metadata when using agentic RAG:
- `agentIterations`: number of agent loop iterations used
- `agentReplans`: number of replans used
- `agentToolCalls`: list of tools called with arguments and result counts
- `agentThoughts`: agent reasoning for each iteration (optional)
- `agentQueryPlan`: sanitized intent, sections, and required fields
- `agent.durationMs`, `agent.tokenUsage`, and optional `agent.error` diagnostics

### Feature Flag and Rollback

The system uses Agentic RAG exclusively. If the agent loop fails before a final answer, the service falls back to the existing retrieval search and stores a partial/error-marked local evidence summary instead of letting the Celery task crash.

Voice provider metadata is persisted under `source.voiceMetadata`. Warnings from preprocessing, VAD, ASR, diarization, or missing speech regions are also copied into `quality.warnings` so chat/review surfaces can explain transcript confidence without exposing internal stack traces.

The Ollama guardrail provider uses the simplified safety prompt (`PROMPT_VERSION=v3-simplified`) to help the small model (`llama-guard3:1b`) distinguish business meeting content from real threats. A regex pre-check catches obvious prompt injection patterns before calling the model. Transient Ollama failures can be retried with `GUARDRAIL_MAX_RETRIES` (default `1` across Settings, Compose, and `.env.example`); transport failures and model parse failures remain distinct categories but follow the same strict/non-strict policy. PII redaction is controlled by `GUARDRAIL_PII_REDACTION_ENABLED` and applies to the copy sent to the guardrail model. Trusted grounded answers with citations can receive a conservative false-positive override only when the reported category has no matching content signal. If the provider fails, the fail-open metadata records the measured latency instead of a zero-duration placeholder.

## Configuration

Settings are loaded by `backend/configs/settings.py` using `pydantic-settings`.

| Env var | Default | Purpose |
|---|---|---|
| `APP_NAME` | `Omnicall API` | FastAPI app title and health response app name |
| `APP_ENV` | `local` | Runtime environment label |
| `API_PREFIX` | `/api` | Backend API route prefix |
| `CORS_ORIGINS` | empty list | Allowed browser origins |
| `AUTH_SESSION_TTL_HOURS` | `168` | Bearer session expiry window for local accounts |
| `POSTGRES_*` | local Compose values | PostgreSQL connection settings |
| `RABBITMQ_*` | local Compose values | Celery broker connection settings |
| `PROCESSING_RECONCILIATION_INTERVAL_SECONDS` | `60` | Periodic stale queued-meeting scan interval |
| `PROCESSING_RECONCILIATION_STALE_SECONDS` | `120` | Queued age required before automatic republish |
| `PROCESSING_RECONCILIATION_BATCH_SIZE` | `100` | Maximum meetings republished in one cycle |
| `REDIS_*` | local Compose values | Redis connection and processing lock TTL |
| `MINIO_*` | local Compose values | Object storage settings |
| `PROMETHEUS_URL` | `http://prometheus:9090` | Internal Prometheus URL used only by the backend admin metrics service |
| `ADMIN_METRICS_CACHE_KEY` | `admin:metrics:snapshot` | Redis key for the normalized admin dashboard snapshot |
| `ADMIN_METRICS_CACHE_TTL_SECONDS` | `10` | Short TTL for admin metrics dashboard cache |
| `OPERATIONAL_LOG_STREAM_KEY` | `admin:logs:operational` | Temporary Redis Stream key for processing and RAG events |
| `OPERATIONAL_LOG_MAX_LENGTH` | `1000` | Approximate maximum retained event count |
| `OPERATIONAL_LOG_TTL_SECONDS` | `86400` | Sliding stream TTL refreshed when events are appended |
| `OPERATIONAL_LOG_DEFAULT_TAIL` | `100` | Default number of recent events returned to the Admin UI |
| `UPLOAD_MAX_BYTES` | `524288000` | Backend upload size limit |
| `UPLOAD_ALLOWED_EXTENSIONS` | audio/video extensions | Upload extension allowlist |
| `UPLOAD_ALLOWED_CONTENT_TYPES` | audio/video MIME types | Upload content-type allowlist |
| `VAD_MIN_SPEECH_MS` | `300` | Minimum speech-region duration retained by local VAD |
| `VAD_SILENCE_GAP_MS` | `500` | Maximum silence gap merged into one speech region |
| `VAD_ENERGY_THRESHOLD` | `0.012` | RMS energy threshold used by local VAD |
| `ASR_TIMEOUT_SECONDS` | `120` | Minimum local ASR command timeout |
| `ASR_TIMEOUT_REALTIME_FACTOR` | `1.0` | Multiplies normalized audio duration to extend ASR/diarization subprocess timeouts for longer voice files |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Local Ollama text embedding model |
| `EMBEDDING_DIMENSIONS` | `768` | Expected local text embedding vector size |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | Ollama embedding request timeout |
| `EMBEDDING_BATCH_SIZE` | `16` | Maximum chunk texts sent in one Ollama embedding request |
| `EMBEDDING_MAX_RETRIES` | `2` | Bounded retry count for transient embedding failures |
| `EMBEDDING_RETRY_BACKOFF_SECONDS` | `0.2` | Exponential retry backoff base for embedding requests |
| `EMBEDDING_CONTRACT_VERSION` | `v1` | Embedding contract identity stored with indexed chunks |
| `RERANK_TOP_K` | `12` | Number of retrieval candidates collected before rerank |
| `RERANK_OUTPUT_K` | `6` | Number of reranked chunks returned to chat |
| `RERANK_TIMEOUT_SECONDS` | `30` | Local rerank command timeout |
| `GUARDRAIL_MODEL` | `llama-guard3:1b` | Local Ollama guardrail model optimized for CPU-first request-path checks |
| `GUARDRAIL_TIMEOUT_SECONDS` | `20` | Local Ollama guardrail timeout |
| `GUARDRAIL_MAX_RETRIES` | `0` | Local guardrail retry count |
| `GUARDRAIL_INPUT_ENABLED` | `true` | Enable user question guardrail before retrieval |
| `GUARDRAIL_OUTPUT_ENABLED` | `true` | Enable assistant output guardrail before persistence |
| `GUARDRAIL_STRICT_MODE` | `false` | Guardrail provider errors fail closed (`blocked`) when true; otherwise fail open (`allowed` + `provider_error`) |
| `GUARDRAIL_PII_REDACTION_ENABLED` | `true` | Redact PII (email, phone, card) in the copy sent to the guardrail model |
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
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Compose Ollama service URL used for local fallback generation, embeddings, and guardrail checks |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | Small local fallback model |
| `OLLAMA_LLM_TIMEOUT_SECONDS` | `600` | Local fallback generation timeout, separate from the primary endpoint timeout |
| `OLLAMA_CONTEXT_LENGTH` | `8192` | Context window used for local fallback meeting analysis |
| `AGENTIC_RAG_MAX_ITERATIONS` | `2` | Maximum planner/retrieval/verification iterations |
| `AGENTIC_RAG_MAX_REPLANS` | `1` | Maximum bounded replans after missing evidence |
| `AGENTIC_RAG_MAX_TOOL_CALLS_PER_ITERATION` | `4` | Maximum retrieval tool calls in one iteration |
| `AGENTIC_RAG_MAX_CHUNKS_PER_TOOL` / `AGENTIC_RAG_MAX_TOTAL_CHUNKS` | `5` / `12` | Per-tool and total accumulated chunk limits |
| `AGENTIC_RAG_ITERATION_TIMEOUT_SECONDS` | `30` | Per-iteration agent timeout |
| `AGENTIC_RAG_TOTAL_TIMEOUT_SECONDS` | `60` | Total agent request timeout |
| `AGENTIC_RAG_MAX_CONTEXT_TOKENS` | `4000` | Maximum retrieved context tokens supplied to the agent |
| `RETRIEVAL_FALLBACK_CANDIDATE_LIMIT` | `48` | Maximum degraded PostgreSQL fallback candidate pool |
| `RETRIEVAL_TRIGRAM_THRESHOLD` | `0.12` | Minimum PostgreSQL trigram similarity for degraded retrieval candidates |
| `RATE_LIMIT_ENABLED` | `true` | Enable request rate limiting |
| `RATE_LIMIT_*_PER_MINUTE` | route-specific quotas | Rate-limit quotas for public, auth, meeting, and admin routes |
| `CONCURRENCY_LIMIT_*` | route-specific limits | Maximum concurrent requests by route group |
| `TASK_LIMIT_PER_MEETING` / `TASK_LIMIT_PER_USER` | `2` / `5` | Active meeting-processing task guards |
| `CIRCUIT_BREAKER_ENABLED` | `true` | Enable PostgreSQL, Milvus, and MinIO circuit breakers |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Consecutive failures required to open a breaker |
| `CIRCUIT_BREAKER_RECOVERY_SECONDS` | `30` | Recovery window before a half-open probe |

The settings loader reads a root `.env` file when present. Compose passes application settings to both backend and worker containers, including rate/concurrency/task guards, circuit-breaker thresholds, and Agentic RAG budgets. PostgreSQL, Milvus, and MinIO breakers now read those settings instead of using provider-local constants. The environment exposes deployment addresses, credentials, feature toggles, timeouts, VAD thresholds, retrieval limits, and Ollama model selection. `ollama-init` pulls the configured `OLLAMA_MODEL`, `EMBEDDING_MODEL`, and `GUARDRAIL_MODEL` directly, so no duplicate bootstrap-list variable is needed. Repository-owned local runner details live in `backend/configs/model_runtime.py`: ASR/diarization/rerank model names and commands, CPU/`int8` runtime choices, `/models`, ffmpeg, and the temporary voice directory. Specialized Hugging Face repositories and revisions live in `infras/model-init/model_init.py`.

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
docker compose up -d --build backend worker beat nginx
curl http://127.0.0.1:8080/api/health
```

Run migrations:

```bash
docker compose exec -T backend alembic upgrade head
```

Run backend tests in the backend container:

```bash
docker compose exec -T backend python -m unittest discover -s backend/tests -v
```

Backend tests are grouped by responsibility under `backend/tests/agent`, `api`, `processing`, `providers`, `retrieval`, and `integration`. Shared test doubles remain in `backend/tests/fakes.py`; the test root contains no flat `test_*.py` modules. The discovery command above intentionally starts at `backend/tests` so all groups continue to run together.

Register and call authenticated APIs through the gateway:

```bash
curl -X POST http://127.0.0.1:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@omnicall.local","password":"change-me","display_name":"Local User"}'
```

Create and process a meeting through the gateway:

```bash
curl -X POST http://127.0.0.1:8080/api/meetings \
  -H "X-User-ID: 11111111-1111-4111-8111-111111111111" \
  -H "X-Workspace-ID: 22222222-2222-4222-8222-222222222222" \
  -H "Content-Type: application/json" \
  -d '{}'
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

Phase 8 operational-log verification on 2026-06-19 confirmed:

| Check | Result |
|---|---|
| Alembic current revision | `0001_initial_schema (head)` |
| Backend syntax compile in container | Passed |
| Full backend unittest suite | 62 tests passed after the 9-table schema consolidation |
| Targeted auth/file/admin tests | Passed |
| Frontend TypeScript/Vite build | Passed |
| Gateway smoke for register/login/me/admin metrics/file library/admin delete | Passed |
| Compose config | Passed |
| Gateway smoke for default User registration and admin role management | Passed |
| Admin account deletion and cleanup tests | Passed |
| Account deletion processing-lock, queued-job revoke, and metrics-cache invalidation tests | Passed |

### Phase 25 Hierarchical Intelligence Model

Meeting processing keeps the complete transcript as the authoritative evidence document, then creates deterministic token-bounded transcript windows. Each window is persisted in `meeting_transcript_windows` with ordered segment references, status, retry metadata, and local extraction JSON. The worker fans out bounded LLM extraction across windows and reduces results into `meeting-intelligence-result.v2` with `transcript.windows`, `evidence.items`, `knowledge.records`, and `knowledge.relationships`. Records use canonical types, subtype payloads, evidence references, source references, and derivation metadata.

PostgreSQL remains authoritative for transcript windows, the result JSON, and retrieval chunks. Milvus receives only derived embeddings. Retrieval exposes a compatibility view of unified records to the existing chunk builders, so global records, summaries, relationships, and transcript windows remain searchable without sending the complete transcript to any one LLM request. Failed windows can be retried independently through `omnicall.processing.extract_transcript_window`.

*Document reflects project state during **Phase 39 Agentic RAG v2 Alignment**. Backend owns canonical record planning, retrieval orchestration, evidence verification, bounded replanning, synthesis, and verified evidence-to-citation mapping; provider candidates are normalized into the hierarchical v2 knowledge boundary before persistence.*

## Agentic RAG Runtime Details (Phase 26)

The Agentic RAG system replaces the linear RAG pipeline with an agent-driven approach that can dynamically select tools and perform multi-hop reasoning.

### Architecture

```text
User Question
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│                    AgenticRAGService                         │
│                                                              │
│  ┌─────────────────┐                                        │
│  │ Fast Path Check │──→ greeting/chitchat → fast_path       │
│  └────────┬────────┘                                        │
│           │ meeting question                                 │
│           ▼                                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Query Plan → Retrieve → Verify (max 2 iterations)       ││
│  │                                                         ││
│  │  Missing fields → one bounded replan                    ││
│  └─────────────────────────────────────────────────────────┘│
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │   Synthesize    │──→ grounded/partial/not_enough         │
│  └─────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

### Services

| Service | File | Purpose |
|---------|------|---------|
| `AgenticRAGService` | `services/agent/service.py` | Main agent loop: Think → Execute → Observe → Synthesize |
| `AgentToolRegistry` | `services/agent/tool_registry.py` | Tool lookup, schema formatting, and dispatch |
| `FastPathHandler` | `services/agent/fast_path.py` | Fast path categories such as greeting, chitchat, guidance, and thanks |
| `AgentContextManager` | `services/agent/context_manager.py` | Context accumulation, deduplication, chunk limits |
| `TokenManager` | `services/agent/token_management.py` | Token counting, truncation, budget management |
| `ParallelToolExecutor` | `services/agent/parallel_executor.py` | Parallel tool execution with async |

### Tools Available

| Tool | Type | Description |
|------|------|-------------|
| `search_semantic` | Search | Vector embedding search via Milvus |
| `search_keyword` | Search | PostgreSQL full-text ILIKE search |
| `search_section` | Search | Filter by section type |
| `get_summary` | Retrieval | Executive/detailed summary chunks |
| `search_records` | Retrieval | Generic record/subtype/relation/answer-shape query over `knowledge.records` |

### Evidence States

| State | Description |
|-------|-------------|
| `fast_path` | Immediate response without search (greeting, chitchat, guidance) |
| `grounded` | Answer based on sufficient context with citations |
| `partial` | Answer based on partial context |
| `not_enough_evidence` | No relevant context or required fields found after the bounded retrieval flow |
| `blocked` | Blocked by input/output guardrail |
| `error` | System error |

### Configuration

```env
AGENTIC_RAG_MAX_ITERATIONS=2
AGENTIC_RAG_MAX_REPLANS=1
AGENTIC_RAG_MAX_TOOL_CALLS_PER_ITERATION=4
AGENTIC_RAG_MAX_CHUNKS_PER_TOOL=5
AGENTIC_RAG_MAX_TOTAL_CHUNKS=12
AGENTIC_RAG_ITERATION_TIMEOUT_SECONDS=30.0
AGENTIC_RAG_TOTAL_TIMEOUT_SECONDS=60.0
```

### SSE Events

| Event | Description |
|-------|-------------|
| `agent_think` | Agent thinking with iteration number |
| `agent_plan` | Sanitized intent, sections, and sub-query count |
| `agent_search` | Tools being called |
| `observation` | Tool results (chunks found) |
| `agent_verify` | Evidence sufficiency and missing fields |
| `agent_replan` | Bounded replan status and missing fields |
| `agent_synthesize` | Final answer generation |
| `fast_path` | Immediate response without search |

## Generic Query Graph (Phase 40)

JSON-v2 Agentic RAG uses five tools: `search_semantic`, `search_keyword`, `search_records`, `search_section`, and `get_summary`. `search_records` accepts record type/subtype selectors, relation capabilities, and an answer shape. The planner emits `recordTypes`, `recordSubtypes`, `relationTypes`, `requiredFields`, and `answerShape`; replans preserve those selectors. The verifier checks both fields and requested relations. Common projections (`count`, `participant_list`, `actor_target`, `location`, and `timeline`) are synthesized deterministically from record fields and evidence before the general LLM synthesis path. Transcript speaker labels remain source data; speaker profiles/counts are participant/fact records.

*Document reflects project state during **Phase 40 Generic Query Graph and Answer Projections**. Backend owns identity-aware v2 records, relationship-aware retrieval, evidence verification, and generic answer projection; remaining work is runtime identity-resolution migration.*
