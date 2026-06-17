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
│   ├── admin_controller.py        <- Admin metrics and admin meeting deletion route handlers
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
│   ├── admin_dto.py               <- Admin metrics response contracts
│   ├── auth_dto.py                <- Auth request/response contracts
│   ├── health_dto.py              <- Health response contract
│   ├── file_dto.py                <- Account file response contracts
│   └── meeting_dto.py             <- Meeting API request/response contracts
├── migrations/
│   ├── env.py                     <- Alembic environment
│   └── versions/
│       ├── 0001_core_meeting_records.py
│       ├── 0002_meeting_intelligence_results.py
│       ├── 0003_meeting_intelligence_indexes.py
│       ├── 0004_meeting_chunks.py
│       ├── 0005_chat_history.py
│       ├── 0006_auth_files_audit.py
│       └── 0007_normalize_product_roles.py
├── middlewares/
│   ├── __init__.py
│   └── request_id_middleware.py   <- `X-Request-ID` response header middleware
├── model_runners/
│   ├── __init__.py
│   ├── asr.py                     <- faster-whisper CLI runner for local ASR
│   ├── diarization.py             <- WeSpeaker CLI runner for local diarization
│   └── rerank.py                  <- SentenceTransformers cross-encoder CLI runner for local rerank
├── models/
│   ├── __init__.py
│   ├── core_models.py             <- User, workspace, membership, session, audit models
│   ├── enums.py                   <- Meeting and processing status enums
│   └── meeting_models.py          <- Meeting, asset, job, result, transcript segment, insight, chunk, account file models
├── providers/
│   ├── __init__.py
│   ├── analysis_provider.py       <- LLM-backed processed JSON provider and result normalization
│   ├── app_metrics_provider.py    <- Prometheus application metrics registry and middleware
│   ├── cache_provider.py          <- Redis JSON cache adapter
│   ├── embedding_provider.py      <- Ollama text embedding provider
│   ├── guardrail_provider.py      <- Ollama guardrail provider boundary
│   ├── llm_provider.py            <- LLM provider adapters and Ollama fallback selection
│   ├── lock_provider.py           <- Redis lock provider for worker idempotency
│   ├── prometheus_provider.py     <- Internal Prometheus HTTP query adapter
│   ├── queue_provider.py          <- Celery task publishing adapter
│   ├── rerank_provider.py         <- Local model rerank command boundary
│   ├── storage_provider.py        <- MinIO object storage adapter
│   ├── text_extraction_provider.py <- Text transcript and notes extraction adapter
│   ├── transcript_types.py        <- Shared transcript segment value type
│   ├── transcription_provider.py  <- Text/voice transcription routing provider
│   ├── vector_provider.py         <- Milvus REST vector index adapter and PostgreSQL fallback switch
│   └── voice_provider.py          <- Voice preprocessing, VAD, ASR, and diarization provider contracts
├── repositories/
│   ├── __init__.py
│   ├── auth_repository.py         <- User/workspace/membership/session/audit persistence
│   ├── chat_repository.py         <- Chat session and message persistence
│   ├── file_repository.py         <- Account file persistence
│   ├── meeting_repository.py      <- Meeting, asset, job, result persistence
│   └── retrieval_repository.py    <- Retrieval chunk persistence
├── services/
│   ├── __init__.py
│   ├── admin_meeting_service.py   <- Admin-only meeting deletion and cascading cleanup use case
│   ├── admin_metrics_service.py   <- Admin metrics aggregation and Redis cache use case
│   ├── auth_service.py            <- Registration, login, logout, and current account use cases
│   ├── chat_service.py            <- Meeting-grounded chat use case
│   ├── file_service.py            <- Account file library use cases
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
| `GET` | `/api/me` | Current account, workspace, and role |
| `GET` | `/api/files` | Account-scoped uploaded files |
| `POST` | `/api/files` | Upload an account-scoped file |
| `GET` | `/api/files/{fileId}/content` | Authorized account file bytes for playback/download |
| `DELETE` | `/api/files/{fileId}` | Delete an owned unlinked account file |
| `POST` | `/api/meetings` | Created meeting shell |
| `GET` | `/api/meetings` | Meetings visible in the current workspace |
| `GET` | `/api/meetings/{meetingId}` | Meeting detail and status |
| `POST` | `/api/meetings/{meetingId}/assets` | Uploaded audio/video/text asset metadata; one asset per meeting |
| `GET` | `/api/meetings/{meetingId}/assets/{assetId}/content` | Authorized uploaded asset bytes for browser playback or download |
| `POST` | `/api/meetings/{meetingId}/process` | Processing job queued or visible queue failure |
| `GET` | `/api/meetings/{meetingId}/processing-status` | Meeting status plus latest processing job and latest uploaded asset |
| `GET` | `/api/meetings/{meetingId}/transcript` | Transcript, citations, and quality sections from the processed JSON |
| `GET` | `/api/meetings/{meetingId}/insights` | Summary, analysis, citations, and quality sections from the processed JSON |
| `GET` | `/api/meetings/{meetingId}/intelligence-result` | Complete `meeting_intelligence_result` JSON |
| `POST` | `/api/meetings/{meetingId}/chat` | Ask a question grounded in one processed meeting |
| `GET` | `/api/meetings/{meetingId}/chat/{sessionId}` | Reload saved chat messages for one meeting chat session |
| `GET` | `/api/admin/metrics` | Admin-only normalized operations metrics, cached in Redis |
| `DELETE` | `/api/admin/meetings/{meetingId}` | Admin-only meeting session deletion with cascading cleanup |
| `GET` | `/metrics` | Internal Prometheus scrape endpoint |

In the Compose runtime, the backend is not host-published directly. NGINX proxies public `/api/` traffic to `backend:8000` over the internal Docker network.

## Auth Boundary

The primary product auth path is backend-owned bearer sessions. `POST /api/auth/register` creates a local account, workspace membership, session row, and audit event. `POST /api/auth/login` verifies the PBKDF2-HMAC-SHA256 password hash, creates a new bearer session, and records success/failure audit events. `POST /api/auth/logout` revokes the session token hash.

Authenticated requests send:

```text
Authorization: Bearer <session-token>
```

`backend/dependencies/auth.py` resolves the session token hash from `account_sessions`, checks expiry and revocation, and returns `CurrentUserContext`. Product roles are normalized to exactly `Admin` or `User`.

Development header-based auth remains available only as a local fallback when no bearer token is present:

```text
X-User-ID: <uuid>
X-Workspace-ID: <uuid>
```

Optional bootstrap headers:

```text
X-User-Email
X-User-Name
X-Workspace-Name
X-User-Role
```

The fallback validates UUID header values, creates local `users`, `workspaces`, and `workspace_members` records if they do not exist, and returns a `CurrentUserContext`. This is a development boundary, not the frontend product path.

All meeting reads, uploads, and process triggers are scoped by `workspace_id`.

Admin operations APIs use the same current-context dependency plus a backend role check. `GET /api/admin/metrics` and `DELETE /api/admin/meetings/{meetingId}` accept only `Admin` and reject `User` with `403 admin_access_required`. Frontend role checks only hide UI affordances; backend authorization is authoritative.

Earlier foundation/dev rows could contain the legacy role value `owner`. Alembic migration `0007_normalize_product_roles` converts `owner` and lowercase `admin` values to `Admin`, converts lowercase `user` values to `User`, and adds database check constraints so `workspace_members.role` and `account_sessions.role` can only store `Admin` or `User`.

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

The normalized admin response includes:

| Category | Examples |
|---|---|
| Targets | Prometheus scrape target health and last scrape errors |
| Backend | Request rate and p95 latency |
| Application | Meetings by status and chat messages by role |
| Worker | Processing jobs by status |
| Containers | Docker container CPU cores and memory working set for the `omnicall` Compose project |
| Database/cache/queue/storage/vector/gateway | PostgreSQL connections, Redis memory, RabbitMQ queue messages, MinIO usable capacity, Milvus request rate, and NGINX active connections |

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

Alembic migration `0006_auth_files_audit` adds account auth, file library, and audit records:

| Table/Column | Purpose |
|---|---|
| `users.password_hash` | Local password hash for backend-owned login |
| `account_sessions` | Hashed bearer sessions with expiry and revocation |
| `account_files` | Account-scoped uploaded file metadata, MinIO object key, and optional meeting/asset linkage |
| `audit_events` | Security and operational events for auth, file, metrics, upload, and deletion flows |

Alembic migration `0007_normalize_product_roles` normalizes product roles:

| Table | Purpose |
|---|---|
| `workspace_members` | Converts legacy `owner`/`admin` rows to `Admin`, converts `user` rows to `User`, and adds `ck_workspace_members_product_role` |
| `account_sessions` | Converts legacy session role snapshots to `Admin`/`User` and adds `ck_account_sessions_product_role` |

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
| `uq_account_files_object_key` | One account-file record per stored object key |
| `ck_workspace_members_product_role` | Product membership role must be `Admin` or `User` |
| `ck_account_sessions_product_role` | Product session role snapshot must be `Admin` or `User` |

Meeting statuses are `DRAFT`, `UPLOADED`, `QUEUED`, `PROCESSING`, `READY`, and `FAILED`.

Processing job statuses are `PENDING`, `RUNNING`, `RETRYING`, `SUCCEEDED`, `FAILED`, and `CANCELLED`.

## Upload And Queue Flow

Upload flow:

```text
HTTP multipart upload
-> auth context
-> meeting workspace check
-> one-asset-per-meeting check
-> extension/content-type/size/state validation
-> MinIO put_object
-> meeting_assets row
-> linked account_files row
-> meeting status UPLOADED
```

Upload idempotency is preserved for retries with the same `Idempotency-Key`: the backend returns the existing asset row. A different upload request for a meeting that already has an asset returns `409 meeting_already_has_asset`. This enforces the current product rule that one meeting maps to one uploaded or recorded file and one analysis lineage; users create a new meeting for a different file.

Uploaded asset content is read back through `GET /api/meetings/{meetingId}/assets/{assetId}/content`. The endpoint first checks the meeting against the caller workspace, then loads the object bytes through `ObjectStorageProvider`. It returns the stored content type and an inline content-disposition header so the frontend can create an authenticated Blob URL for audio playback without exposing MinIO directly.

Account file uploads use `POST /api/files`. They store private MinIO objects under an account-owned namespace and persist `account_files` metadata with owner, workspace, content type, size, and upload timestamp. `GET /api/files/{fileId}/content` checks owner/workspace authorization before returning bytes. `DELETE /api/files/{fileId}` deletes object bytes and metadata only when the file is not linked to an existing meeting session. Linked file deletion returns `409 file_linked_to_meeting`; the cleanup path is admin meeting-session deletion.

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

## Meeting Session Deletion Flow

`DELETE /api/admin/meetings/{meetingId}` is implemented in `AdminMeetingService` and requires an `Admin` context.

The use case loads the meeting within the admin workspace, collects all related object keys, deletes linked account file records, deletes chat sessions/messages, transcript segments, insights, retrieval chunks, processed JSON, processing jobs, meeting asset metadata, and the meeting row, then removes object bytes from MinIO. It also asks the vector provider to delete derived Milvus vectors for the meeting. Vector cleanup errors are recorded as derived-infrastructure failures and do not expose internal details to the client.

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
| ASR | `LocalASRProvider` | Runs a configured `ASR_COMMAND` Whisper-compatible CLI/wrapper, parses JSON segments, and maps them into `TranscriptSegment[]` |
| Diarization | `LocalCommandDiarizationProvider` | Runs a configured `DIARIZATION_COMMAND` WeSpeaker-oriented wrapper and merges speaker assignments into transcript segments |
| Analysis | `LLMAnalysisProvider` | Calls the configured LLM provider, retries once with a repair prompt if the provider echoes input or omits required intelligence sections, merges generated sections into the canonical result shape, and preserves the authoritative transcript |
| LLM | `OpenAICompatibleLLMProvider`, `CustomJSONEndpointLLMProvider`, `OllamaLLMProvider`, `FallbackLLMProvider` | Selects API/private endpoint/Ollama providers, tries the configured API/endpoint primary before Ollama fallback, and records the effective provider/model that actually generated the result |
| Text embedding | `OllamaEmbeddingProvider` | Calls local Ollama `/api/embed` with `EMBEDDING_MODEL=nomic-embed-text` and validates the configured vector dimension |
| Vector index | `MilvusVectorProvider`, `NoopVectorProvider` | Upserts derived chunk vectors to Milvus through REST and falls back to PostgreSQL ranking when vector search is unavailable |
| Rerank | `LocalModelRerankProvider` | Runs a configured `RERANK_COMMAND` specialized local reranker and records unavailable metadata when the command is not configured |
| Guardrail | `OllamaGuardrailProvider` | Runs local Ollama checks for transcript, chat input, retrieved context, and assistant output, returning normalized allow/warn/redact/block metadata |

## Local Model Runners

The production local model paths are implemented as command runners under `backend/model_runners/` and invoked through provider command templates. This keeps model runtime code behind provider boundaries while letting backend and worker containers share the same image and `model_cache` volume.

| Runner | Command module | Model/runtime | Output contract |
|---|---|---|---|
| ASR | `python -m backend.model_runners.asr` | `faster-whisper` CPU `int8` over the downloaded Whisper snapshot in `/models/asr` | JSON transcript segments with stable IDs, timestamps, text, and confidence |
| Diarization | `python -m backend.model_runners.diarization` | WeSpeaker speaker embedding/diarization over the downloaded snapshot in `/models/diarization` | JSON turns and segment-to-speaker assignments |
| Rerank | `python -m backend.model_runners.rerank` | SentenceTransformers `CrossEncoder` over `/models/rerank` | JSON ranked chunk IDs |

The diarization runner handles the WeSpeaker Hugging Face snapshot shape used by `Wespeaker/wespeaker-voxceleb-resnet34-LM`, including the `avg_model` file alias expected by WeSpeaker. It also uses a WAV loader compatibility patch for CPU containers where the installed `torchaudio` backend cannot decode standard WAV files directly.

Local Compose now includes an `ollama` service. Backend and worker call it through `OLLAMA_BASE_URL=http://ollama:11434`. Text transcript uploads can produce transcript segments without ASR. Voice uploads use the default local ASR and diarization command templates in `.env`/`.env.example`, which call the repository-owned model runners above. Phase 5.5 added voice contracts, ffmpeg preprocessing, local energy VAD, local ASR and diarization runners, Ollama text embeddings, and local model rerank. Phase 5.6 added Ollama guardrails around transcript processing and chat.

After each successful processing run, the worker persists the full JSONB result and then rebuilds `transcript_segments`, `meeting_insights`, and `meeting_chunks`. These rows are derived lookup/index records for retrieval, filtering, and citations; the JSONB result remains the authoritative product artifact.

Retrieval chunks are built from structured processed JSON sections first, including summary, detailed summary, key points, decisions, action items, important notes, timeline, risks, blockers, dependencies, follow-ups, open questions, topics, entities, and important quotes when present. The indexer accepts both object-shaped items (`text`, `summary`, `task`, `item`, `quote`, `name`, and related keys) and string-shaped items from LLM output. It also maps `citationIds` to stored citation metadata and maps segment references such as `cites: ["seg-070"]` into segment/time metadata when the matching citation exists. Transcript segment chunks are also created as fallback evidence. Low-signal transcript text is skipped for retrieval indexing, but the original transcript remains preserved inside `meeting_intelligence_results.result_json`.

When `VECTOR_PROVIDER=milvus`, `RetrievalIndexService` also upserts derived vectors to the Milvus REST API after `meeting_chunks` are persisted. The upsert payload includes stable derived references: workspace ID, meeting ID, result ID, chunk ID, JSON pointer, source type, section type, and time range. Milvus failures are recorded in job `retrievalMetadata.vectorIndex` and do not fail the meeting because Milvus is derived infrastructure.

## Meeting Chat Flow

Chat is scoped to a single `READY` meeting. The backend checks the workspace/meeting boundary before reading chunks or chat history.

Question flow:

```text
POST /api/meetings/{meetingId}/chat
-> auth context
-> meeting workspace and READY-state check
-> create or load chat_session
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

Retrieval search prefers Milvus when available, then reloads the returned `chunk_id` values from PostgreSQL within the authorized workspace and meeting. If Milvus is unavailable, empty, or returns an error, the service falls back to PostgreSQL ranking over persisted `meeting_chunks`, combining lexical overlap, model embedding similarity, and structured-section priority. PostgreSQL records are always the authoritative chunks returned to chat. For common Vietnamese and English meeting-intelligence questions, retrieval pins the relevant structured sections before rerank: overview/key-point questions pin executive summary, detailed summary, key points, and topics; reason/cause questions pin detailed summary, requirements, constraints, blockers, and key points; return/refund/process questions pin detailed summary, requirements, constraints, blockers, follow-ups, and key points; action questions pin action items/follow-ups/decisions; risk questions pin risks/blockers/open questions; decision/outcome questions pin decisions/outcomes; and timeline questions pin timeline/follow-up sections. This prevents broad Vietnamese questions from being answered only from semantically noisy transcript snippets.

If no chunks meet the evidence threshold, chat returns a `not_enough_evidence` answer and saves it without citations. If input guardrails block the user question, the service stores a safe placeholder user message and a safe assistant refusal without calling retrieval or the answer LLM. If retrieved context is suspicious because it has prompt-injection, jailbreak, system-prompt, exfiltration, or bypass categories, answer generation is skipped. In non-strict local mode, other retrieved-context block decisions from the local guardrail model are downgraded to auditable warnings so normal customer-support, refund, order, or contact-detail meeting context does not overblock answers. If output guardrails block an unsupported answer, the assistant response is downgraded to `not_enough_evidence`. Provider prompts and raw provider responses are not saved in chat history.

Answer prompts instruct the LLM to behave like a meeting intelligence analyst: prefer structured meeting intelligence over raw transcript fragments, synthesize the most relevant evidence, include concrete details for topics, issues, reasons, decisions, risks, timelines, and next actions, and use `not_enough_evidence` only when the retrieved context truly does not support the answer. Assistant message metadata includes the effective LLM provider/model, rerank provider/model/input/output counts, and guardrail action/category/provider/model/confidence/latency metadata so answer generation, retrieval ordering, and guardrail decisions can be observed without storing LLM prompts, rerank prompts, guardrail prompts, or raw provider responses.

Voice provider metadata is persisted under `source.voiceMetadata` and job `providerMetadata.voiceMetadata`. Warnings from preprocessing, VAD, ASR, diarization, or missing speech regions are also copied into `quality.warnings` so chat/review surfaces can explain transcript confidence without exposing internal stack traces.

Transcript guardrail metadata is persisted under `source.guardrails.transcript` and job `providerMetadata.guardrails.transcript`. Guardrail warnings are copied into `quality.warnings`. In non-strict mode, provider outages or suspicious transcript content become auditable warnings; in strict mode, provider outages or blocked transcript checks fail processing with a safe failure reason.

The Ollama guardrail provider is tuned for the CPU-first local runtime. Long transcript and retrieved-context checks are compacted to bounded first/middle/final samples before calling Ollama, and the provider requests a short classifier response with a small context window (`num_ctx=1024`, `num_predict=16`). This keeps `llama-guard3:1b` from timing out on long voice-derived transcripts while still preserving an auditable local safety check. If the provider still fails, the fail-open/fail-closed metadata records the measured latency instead of a zero-duration placeholder.

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
| `REDIS_*` | local Compose values | Redis connection and processing lock TTL |
| `MINIO_*` | local Compose values | Object storage settings |
| `PROMETHEUS_URL` | `http://prometheus:9090` | Internal Prometheus URL used only by the backend admin metrics service |
| `ADMIN_METRICS_CACHE_KEY` | `admin:metrics:snapshot` | Redis key for the normalized admin dashboard snapshot |
| `ADMIN_METRICS_CACHE_TTL_SECONDS` | `10` | Short TTL for admin metrics dashboard cache |
| `UPLOAD_MAX_BYTES` | `524288000` | Backend upload size limit |
| `UPLOAD_ALLOWED_EXTENSIONS` | audio/video/text transcript extensions | Upload extension allowlist |
| `UPLOAD_ALLOWED_CONTENT_TYPES` | audio/video/text transcript MIME types | Upload content-type allowlist |
| `MODEL_CACHE_DIR` | `/models` | Container path for the shared `model_cache` volume used by local model commands |
| `HF_HOME` | `/models/.hf-cache` | Hugging Face cache path used by `model-init` |
| `VOICE_FFMPEG_PATH` | `ffmpeg` | ffmpeg executable used to normalize audio/video assets |
| `VOICE_WORK_DIR` | `/tmp/omnicall-audio` | Worker-local directory for derived temporary audio files |
| `VAD_MIN_SPEECH_MS` | `300` | Minimum speech-region duration retained by local VAD |
| `VAD_SILENCE_GAP_MS` | `500` | Maximum silence gap merged into one speech region |
| `VAD_ENERGY_THRESHOLD` | `0.012` | RMS energy threshold used by local VAD |
| `ASR_MODEL` | `whisper-small-int8` | Local ASR model identifier passed to `ASR_COMMAND` |
| `ASR_COMPUTE_TYPE` | `int8` | Local ASR compute mode passed to `ASR_COMMAND` |
| `ASR_COMMAND` | `python -m backend.model_runners.asr ...` | Default faster-whisper runner command. Supports `{audio_path}`, `{language}`, `{model}`, `{compute_type}`, and `{model_cache_dir}` placeholders and expects JSON on stdout |
| `ASR_HF_REPO` | `Systran/faster-whisper-small` | Hugging Face repo downloaded into `/models/asr` by `model-init` |
| `ASR_HF_REVISION` | `main` | ASR model revision downloaded by `model-init` |
| `ASR_DOWNLOAD_COMMAND` | empty | Optional custom ASR download command for `model-init` |
| `ASR_TIMEOUT_SECONDS` | `120` | Local ASR command timeout |
| `DIARIZATION_MODEL` | `wespeaker-voxceleb-resnet34` | Local speaker embedding/diarization model identifier |
| `DIARIZATION_COMMAND` | `python -m backend.model_runners.diarization ...` | Default WeSpeaker runner command. Supports `{audio_path}`, `{model}`, and `{model_cache_dir}`, receives JSON on stdin, and returns speaker assignments as JSON on stdout |
| `DIARIZATION_HF_REPO` | `Wespeaker/wespeaker-voxceleb-resnet34-LM` | Hugging Face repo downloaded into `/models/diarization` by `model-init` |
| `DIARIZATION_HF_REVISION` | `main` | Diarization model revision downloaded by `model-init` |
| `DIARIZATION_DOWNLOAD_COMMAND` | empty | Optional custom diarization download command for `model-init` |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Local Ollama text embedding model |
| `EMBEDDING_DIMENSIONS` | `768` | Expected local text embedding vector size |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | Ollama embedding request timeout |
| `RERANK_MODEL` | `bge-reranker-v2-m3` | Local reranker model identifier passed to `RERANK_COMMAND` |
| `RERANK_COMMAND` | `python -m backend.model_runners.rerank ...` | Default SentenceTransformers cross-encoder runner command. Supports `{model}` and `{model_cache_dir}`, receives query/chunks JSON on stdin, and returns ranked chunk IDs |
| `RERANK_HF_REPO` | `BAAI/bge-reranker-v2-m3` | Hugging Face repo downloaded into `/models/rerank` by `model-init` |
| `RERANK_HF_REVISION` | `main` | Rerank model revision downloaded by `model-init` |
| `RERANK_DOWNLOAD_COMMAND` | empty | Optional custom rerank download command for `model-init` |
| `RERANK_TOP_K` | `12` | Number of retrieval candidates collected before rerank |
| `RERANK_OUTPUT_K` | `6` | Number of reranked chunks returned to chat |
| `RERANK_TIMEOUT_SECONDS` | `30` | Local rerank command timeout |
| `GUARDRAIL_MODEL` | `llama-guard3:1b` | Local Ollama guardrail model optimized for CPU-first request-path checks |
| `GUARDRAIL_TIMEOUT_SECONDS` | `20` | Local Ollama guardrail timeout |
| `GUARDRAIL_MAX_RETRIES` | `0` | Local guardrail retry count |
| `GUARDRAIL_INPUT_ENABLED` | `true` | Enable user question guardrail before retrieval |
| `GUARDRAIL_TRANSCRIPT_ENABLED` | `true` | Enable transcript guardrail before analysis generation |
| `GUARDRAIL_CONTEXT_ENABLED` | `true` | Enable retrieved context guardrail before answer generation |
| `GUARDRAIL_OUTPUT_ENABLED` | `true` | Enable assistant output guardrail before persistence |
| `GUARDRAIL_STRICT_MODE` | `false` | Fail closed on guardrail provider errors when true; otherwise fail open with warnings |
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
| `OLLAMA_BOOTSTRAP_MODELS` | `qwen2.5:1.5b nomic-embed-text llama-guard3:1b` | Models pulled by `ollama-init` into `ollama_data` |

The settings loader reads a root `.env` file when present. For bootstrap-only model variables, Compose uses default values when a variable is unset and treats an explicitly empty value as an intentional skip. This applies to `OLLAMA_BOOTSTRAP_MODELS`, `ASR_HF_REPO`, `ASR_DOWNLOAD_COMMAND`, `DIARIZATION_HF_REPO`, `DIARIZATION_DOWNLOAD_COMMAND`, `RERANK_HF_REPO`, and `RERANK_DOWNLOAD_COMMAND`.

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

Register and call authenticated APIs through the gateway:

```bash
curl -X POST http://127.0.0.1:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@omnicall.local","password":"change-me-123","display_name":"Admin","role":"Admin"}'
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

Phase 7 verification on 2026-06-17 also confirmed:

| Check | Result |
|---|---|
| Alembic current revision | `0007_normalize_product_roles (head)` |
| Backend syntax compile in container | Passed |
| Full backend unittest suite | 71 tests passed |
| Targeted auth/file/admin tests | Passed |
| Frontend TypeScript/Vite build | Passed |
| Gateway smoke for register/login/me/admin metrics/file library/admin delete | Passed |
| Compose config | Passed |

*Document reflects project state after Phase 7 hardening verification on **2026-06-17**. Backend compile, Compose config, Alembic `0007_normalize_product_roles`, bearer auth, local register/login/logout/me, PBKDF2 password hashing, session revocation, Admin/User database role constraints, Admin/User backend role checks, account file library APIs, protected file playback, blocked linked-file deletion, admin meeting-session deletion cascade, MinIO object cleanup, Milvus derived-vector deletion call, audit events, processed JSON read APIs, authorized uploaded asset content reads, derived transcript/insight/chunk indexes, flexible processed-JSON chunk indexing, Vietnamese/English retrieval intent pinning, analyst-style chat answer prompts, Ollama text embeddings, Milvus REST vector upsert/search with PostgreSQL authoritative reload and dimension recovery, voice/rerank/guardrail providers, meeting chat APIs, chat persistence, source citations, full backend tests, frontend build, and live gateway phase 7 smoke are verified.*
