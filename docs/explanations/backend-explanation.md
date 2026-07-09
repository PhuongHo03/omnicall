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
│   ├── analysis_provider.py       <- LLM-backed processed JSON provider and result normalization
│   ├── app_metrics_provider.py    <- Prometheus application metrics registry and middleware
│   ├── cache_provider.py          <- Redis JSON cache adapter
│   ├── embedding_provider.py      <- Ollama text embedding provider
│   ├── guardrail_provider.py      <- Ollama guardrail provider boundary
│   ├── llm_provider.py            <- LLM provider adapters and Ollama fallback selection
│   ├── lock_provider.py           <- Redis lock provider for worker idempotency
│   ├── operational_log_provider.py <- Temporary bounded Redis Stream adapter
│   ├── prometheus_provider.py     <- Internal Prometheus HTTP query adapter
│   ├── queue_provider.py          <- Celery task publishing adapter
│   ├── circuit_breaker.py         <- Generic circuit breaker with Prometheus metrics
│   ├── rerank_provider.py         <- Local model rerank command boundary
│   ├── storage_provider.py        <- MinIO object storage adapter
│   ├── text_extraction_provider.py <- Text transcript and notes extraction adapter
│   ├── transcript_types.py        <- Shared transcript segment value type
│   ├── transcription_provider.py  <- Text/voice transcription routing provider
│   ├── vector_provider.py         <- Milvus REST vector index adapter and PostgreSQL fallback switch
│   └── voice_provider.py          <- Voice preprocessing, VAD, ASR, and diarization provider contracts
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
│   │   ├── fast_path.py           <- Fast path handler for common queries without retrieval
│   │   ├── parallel_executor.py   <- Parallel tool execution with timeout and partial-failure handling
│   │   ├── service.py             <- Main Agentic RAG orchestration loop
│   │   ├── token_management.py    <- Token counting, limits, and budget management
│   │   └── tool_registry.py       <- Agent tool definitions and execution
│   ├── auth_service.py            <- Registration, login, logout, and current account use cases
│   ├── chat_service.py            <- Meeting-grounded chat use case
│   ├── file_service.py            <- Account file library use cases
│   ├── health_service.py          <- Health use case
│   ├── intelligence_service.py    <- Processed JSON read use cases
│   ├── meeting_service.py         <- Meeting upload and processing use cases
│   ├── operational_log_service.py <- Structured processing/RAG event sanitization, tail, and clear use case
│   ├── processing_pipeline_service.py <- Worker processing use case
│   ├── processing_reconciliation_service.py <- Stale pending-job recovery use case
│   ├── retrieval_chunk_builder.py <- Pure processed JSON to retrieval chunk builder
│   ├── retrieval_index_service.py <- Retrieval indexing orchestration and vector upsert
│   ├── agent_context_manager.py <- Compatibility wrapper for `services/agent/context_manager.py`
│   ├── fast_path_handler.py     <- Compatibility wrapper for `services/agent/fast_path.py`
│   ├── retrieval_search_service.py <- Milvus search with PostgreSQL authoritative record reload and fallback ranking
│   └── token_management.py      <- Compatibility wrapper for `services/agent/token_management.py`
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
| `POST` | `/api/meetings/{meetingId}/assets` | Uploaded audio/video/text asset metadata; one asset per meeting |
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

`DELETE /api/meetings/{meetingId}` is available to authenticated `User` and `Admin` accounts for meetings they own. It uses the production cleanup path: acquire the meeting processing lock, revoke queued processing jobs by ID, delete worker-derived rows and objects, invalidate the admin metrics cache, and release the lock. If processing is actively running and the lock cannot be acquired, it returns `409 meeting_processing_in_progress`. A request for another account's meeting returns `404 meeting_not_found`.

Admin operations APIs use the same current-context dependency plus a backend role check. `GET /api/admin/metrics`, `DELETE /api/admin/meetings/{meetingId}`, account role updates, and account deletion accept only `Admin` and reject `User` with `403 admin_access_required`. Frontend role checks only hide admin portal affordances; backend authorization is authoritative.

`GET /api/admin/accounts` lists local accounts with display name, email, role, creation time, and whether the current admin may change the role. `PATCH /api/admin/accounts/{userId}/role` accepts only `Admin` or `User`, updates `users.role`, records `admin.account.role_update`, and rejects attempts to change the caller's own role with `409 cannot_change_own_role`.

`DELETE /api/admin/accounts/{userId}` deletes another account only. It rejects self-deletion with `409 cannot_delete_own_account`. Before deleting data, it acquires the same Redis processing locks used by workers for every target meeting. If any lock is already held, deletion is blocked with `409 account_meeting_processing_in_progress` so the account cannot be deleted while a worker is mutating its meeting state. When locks are held, it revokes queued Celery processing tasks best-effort by job ID, deletes meetings owned by the target account, removes standalone file-library `meeting_assets` rows and MinIO objects, deletes the user row so sessions and remaining owned rows cascade, invalidates the Redis admin metrics cache, releases the locks, and records `admin.account.delete`.

`DELETE /api/admin/meetings/{meetingId}` uses the same production-grade cleanup path for a single meeting: acquire the meeting processing lock, revoke queued processing jobs by ID, delete worker-derived rows and objects, invalidate the admin metrics cache, and release the lock. If processing is actively running and the lock cannot be acquired, it returns `409 meeting_processing_in_progress`.

The current local-dev baseline has no `workspaces`, `workspace_members`, `account_files`, `chat_sessions`, `transcript_segments`, or `meeting_insights` tables. `users.role` is the authoritative role field.

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

The transcription start event resolves the asset route before logging provider/model context. Text uploads now report `local-text-extraction` with `deterministic-v1`; audio/video uploads report the ASR provider/model and include the voice preprocessing, VAD, and diarization provider details in event metadata. The `LocalTranscriptionProvider` itself remains only a routing boundary named `local-transcription-router` with `routing-v1`, so it is not counted as a separate model.

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
| `workspaces`, `workspace_members` | `users.role` and direct `meetings.owner_user_id` ownership |
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

The use case loads the meeting by ID, collects all related object keys, deletes chat messages, retrieval chunks, processed JSON, meeting asset metadata, and the meeting row, then removes object bytes from MinIO. It also asks the vector provider to delete derived Milvus vectors for the meeting. Vector cleanup errors are recorded as derived-infrastructure failures and do not expose internal details to the client.

The endpoint is safe to retry: a missing meeting returns a successful `{deleted: true}` response for the requested ID, and object deletion ignores missing-object responses.

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

Current provider behavior is model-backed for the six model points. Test-only fakes live under `backend/tests/` and are not production fallbacks.

| Provider | Current adapter | Purpose |
|---|---|---|
| Transcription | `LocalTranscriptionProvider` | Routes text uploads to text extraction and audio assets through voice preprocessing/VAD/ASR/diarization; voice failures raise safe processing errors instead of creating placeholder transcript text |
| Text extraction | `DocumentTextExtractionProvider` | Reads `.txt`, `.md`, `.vtt`, and `.srt` uploads from MinIO and turns timestamp/speaker lines into transcript segments |
| Voice preprocessing | `LocalAudioPreprocessor` | Reads the original asset bytes from MinIO, normalizes supported media to a stable per-asset temporary 16 kHz mono WAV with ffmpeg, deletes raw temp input, reuses valid derived WAVs across retries, and records duration, sample rate, channel count, and warnings |
| VAD | `LocalVADProvider` | Local energy-based speech-region detector over normalized WAV audio, with configurable minimum speech duration, silence merge gap, energy threshold, and speech-region metadata |
| ASR | `LocalASRProvider` | Runs the repository-owned faster-whisper CPU `int8` runner, parses JSON segments, and maps them into `TranscriptSegment[]` |
| Diarization | `LocalCommandDiarizationProvider` | Runs the repository-owned WeSpeaker CPU runner and merges speaker assignments into transcript segments |
| Analysis | `LLMAnalysisProvider` | Calls the configured LLM provider, retries once with a repair prompt if the provider echoes input or omits required intelligence sections, sends transcript evidence to the provider as compact `segmentId|speaker|text` lines to conserve model context, merges generated sections into the canonical result shape, and preserves the full authoritative transcript |
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

Local Compose now includes an `ollama` service. Backend and worker call it through `OLLAMA_BASE_URL=http://ollama:11434`. Text transcript uploads can produce transcript segments without ASR. Voice uploads use the default local ASR and diarization command templates in `.env`/`.env.example`, which call the repository-owned model runners above. Phase 5.5 added voice contracts, ffmpeg preprocessing, local energy VAD, local ASR and diarization runners, Ollama text embeddings, and local model rerank. Phase 5.6 added Ollama guardrails around chat input and output. Phase 15 simplified actions to `allowed`/`blocked` and added regex pre-check, few-shot prompt, and post-verdict category validation.

After each successful processing run, the worker persists the full JSONB result and then rebuilds `meeting_chunks`. The full transcript and structured insight sections stay inside `meeting_intelligence_results.result_json`; the JSONB result remains the authoritative product artifact.

Retrieval chunks are built from the full processed JSON instead of only the narrative summary/analysis fields. `RetrievalIndexService` owns indexing orchestration only, while `retrieval_chunk_builder.py` owns pure chunk construction. The builder creates stable chunks for `meeting` metadata, `source` provider/model/voice/guardrail metadata, participant overview and per-participant records, summary sections, every list-shaped `analysis` section, `analysis.emptySections`, transcript coverage, quality overview/warnings, a compact citation map, and transcript fallback segments. Transcript fallback chunks include speaker, time range, confidence, and text together so questions about who spoke or transcript quality do not have to infer from text alone. Low-signal transcript text is skipped for retrieval indexing, but the original transcript remains preserved inside `meeting_intelligence_results.result_json`.

Structured item text is serialized from meaningful metadata fields instead of selecting only the first text-like field. This keeps owners, assignees, roles, statuses, due dates, priorities, categories, confidence, details, citation IDs, and segment references searchable when the LLM returns rich object-shaped items. The indexer still accepts string-shaped LLM sections and maps `citationIds`, `cites`, `sourceSegmentIds`, and `segmentIds` to stored citation metadata when possible.

When `VECTOR_PROVIDER=milvus`, `RetrievalIndexService` also upserts derived vectors to the Milvus REST API after `meeting_chunks` are persisted. The upsert payload includes stable derived references: meeting ID, result ID, chunk ID, JSON pointer, source type, section type, and time range. Milvus failures are recorded in retrieval metadata and do not fail the meeting because Milvus is derived infrastructure.

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
-> guardrail check retrieved context
-> call LLMProvider with retrieved context
-> fallback to local retrieval summary if the provider fails
-> guardrail check assistant answer
-> save assistant chat_message with retrieved chunk IDs and citations
-> return answer, evidence state, and source citations
```

Retrieval search prefers Milvus when available, then reloads the returned `chunk_id` values from PostgreSQL within the authorized meeting. If Milvus is unavailable, empty, or returns an error, the service falls back to PostgreSQL ranking over persisted `meeting_chunks`, combining lexical overlap, model embedding similarity, and structured-section priority. PostgreSQL records are always the authoritative chunks returned to chat. For common Vietnamese and English meeting-intelligence questions, retrieval pins the relevant structured sections before rerank: participant/count/role questions pin participant chunks; quality/confidence/warning questions pin quality, transcript coverage, and voice metadata; source/model/file questions pin source metadata; meeting-title/duration questions pin meeting metadata; missing-evidence questions pin `analysis.emptySections`; metric/entity/glossary questions pin those analysis sections; overview/key-point questions pin executive summary, detailed summary, key points, and topics; reason/cause questions pin detailed summary, requirements, constraints, blockers, and key points; return/refund/process questions pin detailed summary, requirements, constraints, blockers, follow-ups, and key points; action questions pin action items/follow-ups/decisions; risk questions pin risks/blockers/open questions; decision/outcome questions pin decisions/outcomes; and timeline questions pin timeline/follow-up sections. This prevents broad Vietnamese questions from being answered only from semantically noisy transcript snippets.

If no chunks meet the evidence threshold, chat returns a `not_enough_evidence` answer and saves it without citations. Guardrails now use the simplified `allowed`/`blocked` contract only. If input guardrails block the user question, the service stores a safe assistant refusal without calling the agent. Provider errors fail open as `allowed` with `provider_error` metadata. If output guardrails block an answer, the assistant response is replaced with a safe message and citations are removed. The chat flow no longer expects redacted text, warning actions, or a context guardrail stage. Provider prompts and raw provider responses are not saved in chat history.

Answer prompts live in the Agentic RAG service rather than `MeetingChatService`. Phase 18 removed the unused linear-RAG helper path from `MeetingChatService`, leaving that service focused on permission checks, user/assistant message persistence, guardrail orchestration, agent delegation, SSE status publishing, and operational logs. Assistant message metadata includes agent iterations, tool calls, thoughts, duration, token usage, and guardrail action/categories/provider/model/confidence/latency/promptVersion/textLength/decisionId metadata so answer generation, retrieval ordering, and guardrail decisions can be observed without storing LLM prompts, rerank prompts, guardrail prompts, or raw provider responses. `GET /api/meetings/{meetingId}/chat` returns the authorized meeting thread and messages, allowing the frontend to recover persisted chat after reloads, route changes, or lost browser state.

For local development after changing chunk formats, run `python -m backend.scripts.rebuild_retrieval_index --clear-chat` inside the backend environment to rebuild all PostgreSQL chunks and Milvus vectors from stored `meeting_intelligence_results` and remove chat history that may cite stale chunk IDs. Use `--meeting-id <id>` to target one meeting. A full disposable reset is still possible with Compose volume deletion, migrations, and reprocessing when old local data is not worth preserving.

## Agentic RAG (Phase 16)

The chat service uses `backend.services.agent.AgenticRAGService` for all chat requests after input guardrails pass. The agentic code is grouped under `backend/services/agent/`; old module paths such as `backend.services.agentic_rag_service` remain compatibility wrappers. The agentic flow implements a Think → Execute Tools → Observe loop with up to 3 iterations (configurable via `AGENTIC_RAG_MAX_ITERATIONS`) and a total timeout budget (`AGENTIC_RAG_TOTAL_TIMEOUT_SECONDS`).

### Flow

```
user question
-> input guardrail check
-> fast path detection through the LLM boundary
   -> if fast path: return direct response with evidenceState="fast_path"
-> agent loop (max N iterations):
   -> Think: LLM analyzes question and decides which tools to call
   -> Execute: run selected tools in parallel (semantic search, keyword search, section search, etc.)
   -> Observe: evaluate results and decide to continue or synthesize
   -> if synthesize or last iteration: generate final answer
-> if the agent LLM fails: fall back to the existing retrieval search and local evidence summary
-> output guardrail check
-> save answer with agent metadata (iterations, tool calls, thoughts)
```

LLM JSON generation remains deterministic by default with `temperature=0` for analysis, planning, synthesis, and guardrail-like structured flows. Fast-path detection is the exception: `FastPathHandler` passes `temperature=0.5` for direct greeting, thanks, guidance, and small-talk answers so repeated non-RAG prompts can be less robotic while the response still follows the `{needsRag, answer}` JSON contract.

### Tools

The agent can invoke these tools:
- `search_semantic`: vector embedding search via Milvus
- `search_keyword`: PostgreSQL full-text ILIKE search
- `search_section`: filter chunks by section type
- `search_speaker`: search by speaker name/role
- `get_summary`, `get_action_items`, `get_decisions`, `get_risks`, `get_timeline`, `get_participants`: structured data retrieval
- `synthesize_answer`: trigger final answer generation. Phase 18 restored this tool in the registry dispatch table so the declared tool list, `_VALID_TOOLS`, and execution behavior match.

### SSE Events

The agentic flow emits additional SSE events:
- `connected`: initial stream handshake with `{"type":"connected","status":"connected"}`
- `agent_think`: iteration number and message
- `agent_search`: iteration, tool names, and message
- `observation`: iteration, new chunks found, success/failure counts
- `agent_synthesize`: iteration and whether forced
- `fast_path`: for immediate responses

### Agent Metadata

Assistant chat messages include additional metadata when using agentic RAG:
- `agentIterations`: number of agent loop iterations used
- `agentToolCalls`: list of tools called with arguments and result counts
- `agentThoughts`: agent reasoning for each iteration (optional)
- `agent.durationMs`, `agent.tokenUsage`, and optional `agent.error` diagnostics

### Feature Flag and Rollback

The system uses Agentic RAG exclusively. If the agent loop fails before a final answer, the service falls back to the existing retrieval search and stores a partial/error-marked local evidence summary instead of letting the Celery task crash.

Voice provider metadata is persisted under `source.voiceMetadata`. Warnings from preprocessing, VAD, ASR, diarization, or missing speech regions are also copied into `quality.warnings` so chat/review surfaces can explain transcript confidence without exposing internal stack traces.

The Ollama guardrail provider uses a few-shot Vietnamese prompt (`PROMPT_VERSION=v2`) to help the small model (`llama-guard3:1b`) distinguish business meeting content from real threats. A regex pre-check catches obvious prompt injection patterns before calling the model. Post-verdict category validation overrides false-positive blocks when category keywords do not match the content. If the provider fails, the fail-open metadata records the measured latency instead of a zero-duration placeholder.

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
| `UPLOAD_ALLOWED_EXTENSIONS` | audio/video/text transcript extensions | Upload extension allowlist |
| `UPLOAD_ALLOWED_CONTENT_TYPES` | audio/video/text transcript MIME types | Upload content-type allowlist |
| `VAD_MIN_SPEECH_MS` | `300` | Minimum speech-region duration retained by local VAD |
| `VAD_SILENCE_GAP_MS` | `500` | Maximum silence gap merged into one speech region |
| `VAD_ENERGY_THRESHOLD` | `0.012` | RMS energy threshold used by local VAD |
| `ASR_TIMEOUT_SECONDS` | `120` | Minimum local ASR command timeout |
| `ASR_TIMEOUT_REALTIME_FACTOR` | `1.0` | Multiplies normalized audio duration to extend ASR/diarization subprocess timeouts for longer voice files |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Local Ollama text embedding model |
| `EMBEDDING_DIMENSIONS` | `768` | Expected local text embedding vector size |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | Ollama embedding request timeout |
| `RERANK_TOP_K` | `12` | Number of retrieval candidates collected before rerank |
| `RERANK_OUTPUT_K` | `6` | Number of reranked chunks returned to chat |
| `RERANK_TIMEOUT_SECONDS` | `30` | Local rerank command timeout |
| `GUARDRAIL_MODEL` | `llama-guard3:1b` | Local Ollama guardrail model optimized for CPU-first request-path checks |
| `GUARDRAIL_TIMEOUT_SECONDS` | `20` | Local Ollama guardrail timeout |
| `GUARDRAIL_MAX_RETRIES` | `0` | Local guardrail retry count |
| `GUARDRAIL_INPUT_ENABLED` | `true` | Enable user question guardrail before retrieval |
| `GUARDRAIL_OUTPUT_ENABLED` | `true` | Enable assistant output guardrail before persistence |
| `GUARDRAIL_STRICT_MODE` | `false` | Fail closed on guardrail provider errors when true; otherwise fail open (`allowed` + `provider_error`) |
| `GUARDRAIL_INPUT_STRICT_MODE` | (empty) | Per-layer override for input guardrail strict mode |
| `GUARDRAIL_OUTPUT_STRICT_MODE` | (empty) | Per-layer override for output guardrail strict mode |
| `GUARDRAIL_LATENCY_BUDGET_MS` | `8000` | Cumulative latency budget; output guardrail skipped when exceeded |
| `GUARDRAIL_PII_REDACTION_ENABLED` | `true` | Pre-redact PII (email, phone, card) before sending to guardrail |
| `GUARDRAIL_INPUT_STRICT_MODE` | `` | Per-layer strict mode for input guardrail; falls back to `GUARDRAIL_STRICT_MODE` when empty |
| `GUARDRAIL_OUTPUT_STRICT_MODE` | `` | Per-layer strict mode for output guardrail; falls back to `GUARDRAIL_STRICT_MODE` when empty |
| `GUARDRAIL_LATENCY_BUDGET_MS` | `8000` | Cumulative guardrail latency budget in milliseconds; output guardrail is skipped when exceeded |
| `GUARDRAIL_PII_REDACTION_ENABLED` | `true` | Redact PII (email, phone, card) from answer text before output guardrail check |
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

The settings loader reads a root `.env` file when present. The environment exposes deployment addresses, credentials, feature toggles, timeouts, VAD thresholds, retrieval limits, and Ollama model selection. `ollama-init` pulls the configured `OLLAMA_MODEL`, `EMBEDDING_MODEL`, and `GUARDRAIL_MODEL` directly, so no duplicate bootstrap-list variable is needed. Repository-owned local runner details live in `backend/configs/model_runtime.py`: ASR/diarization/rerank model names and commands, CPU/`int8` runtime choices, `/models`, ffmpeg, and the temporary voice directory. Specialized Hugging Face repositories and revisions live in `infras/model-init/model_init.py`.

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

*Document reflects project state after **Phase 21 Fast Path Temperature Tuning**. Agentic RAG code is grouped under `backend/services/agent/` with compatibility wrappers, retrieval chunk construction is split from indexing orchestration, the initial chat SSE handshake includes a typed JSON payload, LLM JSON generation defaults to deterministic temperature `0`, and fast-path direct responses use a dedicated temperature of `0.5`.*

## Agentic RAG (Phase 16)

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
│  │              Agent Loop (max 3 iterations)              ││
│  │                                                         ││
│  │  ┌──────────┐    ┌──────────────┐    ┌──────────────┐  ││
│  │  │  Think   │───▶│ Execute Tools│───▶│   Observe    │  ││
│  │  │  (LLM)   │    │  (Parallel)  │    │  (Evaluate)  │  ││
│  │  └──────────┘    └──────────────┘    └──────────────┘  ││
│  │       │                                      │          ││
│  │       └──────────────────────────────────────┘          ││
│  │                      loop until done                    ││
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
| `AgenticRAGService` | `services/agentic_rag_service.py` | Main agent loop: Think → Execute → Observe → Synthesize |
| `AgentToolRegistry` | `services/agent_tool_registry.py` | 11 tool definitions and execution |
| `FastPathHandler` | `services/fast_path_handler.py` | Compatibility wrapper for `services/agent/fast_path.py`; handles fast path categories such as greeting, chitchat, guidance, and thanks through the LLM boundary with dedicated response temperature |
| `AgentContextManager` | `services/agent_context_manager.py` | Context accumulation, deduplication, chunk limits |
| `TokenManagement` | `services/token_management.py` | Token counting, truncation, budget management |
| `ParallelToolExecutor` | `services/parallel_tool_executor.py` | Parallel tool execution with async |

### Tools Available

| Tool | Type | Description |
|------|------|-------------|
| `search_semantic` | Search | Vector embedding search via Milvus |
| `search_keyword` | Search | PostgreSQL full-text ILIKE search |
| `search_section` | Search | Filter by section type |
| `search_speaker` | Search | Search by speaker name/role |
| `get_summary` | Retrieval | Executive/detailed summary chunks |
| `get_action_items` | Retrieval | Action items and follow-ups |
| `get_decisions` | Retrieval | Decisions and outcomes |
| `get_risks` | Retrieval | Risks, blockers, open questions |
| `get_timeline` | Retrieval | Timeline and deadlines |
| `get_participants` | Retrieval | Participant information |
| `synthesize_answer` | Synthesis | Trigger final answer generation |

### Evidence States

| State | Description |
|-------|-------------|
| `fast_path` | Immediate response without search (greeting, chitchat, guidance) |
| `grounded` | Answer based on sufficient context with citations |
| `partial` | Answer based on partial context |
| `not_enough_evidence` | No relevant context found after N iterations |
| `blocked` | Blocked by input/output guardrail |
| `error` | System error |

### Configuration

```env
AGENTIC_RAG_MAX_ITERATIONS=3
AGENTIC_RAG_ITERATION_TIMEOUT_SECONDS=30.0
AGENTIC_RAG_TOTAL_TIMEOUT_SECONDS=60.0
```

### SSE Events

| Event | Description |
|-------|-------------|
| `agent_think` | Agent thinking with iteration number |
| `agent_search` | Tools being called |
| `observation` | Tool results (chunks found) |
| `agent_synthesize` | Final answer generation |
| `fast_path` | Immediate response without search |
