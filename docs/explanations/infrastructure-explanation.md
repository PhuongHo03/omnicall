# Infrastructure Explanation

> **Phase 47 authority:** Compose exposes one Simple RAG runtime. There is no legacy/shadow/canary pipeline mode, answer cache, Semantic Cache, or Agent Memory wiring. Older phase text later in this document is historical where it conflicts with this section.

## Simple RAG Runtime And Cutover Safety

Backend and worker receive `DEFAULT_CHAT_LANGUAGE=en`, `RAG_QUERY_INTERPRETATION_TIMEOUT_SECONDS=15`, `RAG_EVIDENCE_RETRIEVAL_TIMEOUT_SECONDS=20`, `RAG_SYNTHESIS_PRIMARY_TIMEOUT_SECONDS=60`, `RAG_SYNTHESIS_FALLBACK_TIMEOUT_SECONDS=40`, `RAG_FINALIZATION_RESERVE_SECONDS=15`, `RAG_CHAT_TURN_TIMEOUT_SECONDS=150`, `RAG_SYNTHESIS_CONTRACT_RETRIES=1`, `LLM_REASONING_MODE=disabled`, and `CHAT_TURN_LEASE_SECONDS=300`. `DEFAULT_CHAT_LANGUAGE` is the fallback BCP 47 locale for clients that do not supply a chat `language`; it accepts `en` or `vi`. `.env`, `.env.example`, typed settings, and both Compose services use the same keys. Contract versions are source constants.

Direct cutover safety is artifact-based: timestamped PostgreSQL dump, asset metadata/MinIO inventory, intelligence fixtures, previous git revision/image IDs, and a successful isolated restore rehearsal. `backend/scripts/direct_cutover_reset.py` is dry-run by default, requires a non-empty backup directory, accepts only the two approved meeting IDs, preserves meeting/asset/source-audio records, and needs explicit `--execute` before removing derived state and queuing reprocessing. Rollback uses previous images and the restore-tested dump, not a runtime feature flag.

## Structure

```text
.
├── .dockerignore                    <- Docker build context ignores for local artifacts
├── .env.example                    <- Runtime configuration template for Compose
├── docker-compose.yml              <- Local stack wiring, networks, volumes, healthchecks
└── infras/
    ├── docker-exporter/
    │   └── exporter.py               <- Internal Docker stats Prometheus exporter
    ├── etcd/
    │   └── etcd.conf.yml             <- Single-node etcd persistence and compaction config
    ├── milvus/
    │   └── user.yaml                 <- Milvus standalone override config
    ├── model-init/
    │   ├── Dockerfile                <- Model bootstrap image
    │   └── model_init.py             <- One-shot ASR/diarization/rerank snapshot bootstrap
    ├── nginx/
    │   └── nginx.conf                <- Public gateway routing
    ├── postgres/
    │   ├── pg_hba.conf               <- Internal PostgreSQL client authentication rules
    │   └── postgresql.conf           <- PostgreSQL runtime and logging config
    ├── prometheus/
    │   └── prometheus.yml            <- Internal Prometheus scrape config
    ├── rabbitmq/
    │   ├── enabled_plugins           <- Management and Prometheus plugins
    │   └── rabbitmq.conf             <- AMQP, management, resource, and logging config
    └── redis/
        └── redis.conf                <- Redis persistence, memory, and network config
```

## Runtime Services

The local runtime is managed through Docker Compose.

| Service | Role | Host Exposure |
|---|---|---|
| `nginx` | Public edge gateway | `${APP_BIND_IP}:${NGINX_PORT}:80` |
| `frontend` | Vite React UI | Internal only, `expose: 5173` |
| `backend` | FastAPI API server | Internal only, `expose: 8000` |
| `worker` | Celery meeting, chat, memory, repair, and maintenance worker | Internal only, no host ports |
| `beat` | Celery periodic reconciliation scheduler | Internal only, no host ports |
| `postgres` | Durable relational state | Internal only, `expose: 5432` |
| `redis` | Disposable RAG/admin cache, locks, singleflight/idempotency keys, transient SSE Pub/Sub, and bounded operational event stream | Internal only, `expose: 6379` |
| `rabbitmq` | Celery broker | AMQP internal, management UI on `${LOCAL_BIND_IP}:${RABBITMQ_MANAGEMENT_PORT}` |
| `minio` | Object storage for meeting assets and Milvus objects | API internal, console on `${LOCAL_BIND_IP}:${MINIO_CONSOLE_PORT}` |
| `etcd` | Milvus metadata dependency | Internal only, `expose: 2379` |
| `adminer` | Local database admin UI | `${LOCAL_BIND_IP}:${ADMINER_PORT}` |
| `milvus` | Vector database for meeting chunks | API internal on `19530`, WebUI on `${LOCAL_BIND_IP}:${MILVUS_WEBUI_PORT}` |
| `prometheus` | Internal metrics scraper | UI on `${LOCAL_BIND_IP}:${PROMETHEUS_PORT}` |
| `redisinsight` | Local Redis admin UI | `${LOCAL_BIND_IP}:${REDIS_INSIGHT_PORT}` |
| `docker-exporter` | Internal Docker container CPU/RAM exporter for Prometheus | Internal only, `expose: 9104` |
| `postgres-exporter` | PostgreSQL Prometheus exporter | Internal only, `expose: 9187` |
| `redis-exporter` | Redis Prometheus exporter | Internal only, `expose: 9121` |
| `nginx-exporter` | NGINX Prometheus exporter | Internal only, `expose: 9113` |

Only NGINX is public by default. Admin/debug UIs are localhost-bound through `LOCAL_BIND_IP`. Backend and infrastructure service protocols stay internal.

## Infrastructure Service Configuration

Compose mounts service configuration files read-only from `infras/`. These files own stable runtime behavior, while `.env` remains the source for credentials and environment-specific values.

| Service | Config | Key behavior |
|---|---|---|
| PostgreSQL | `infras/postgres/postgresql.conf` | SCRAM password storage, connection/memory defaults, statement logging, explicit HBA path |
| PostgreSQL | `infras/postgres/pg_hba.conf` | Trusts the local Unix socket and requires SCRAM for loopback and Docker private-network clients |
| Redis | `infras/redis/redis.conf` | AOF plus snapshot persistence, 512 MB cap, `noeviction`, protected mode |
| RabbitMQ | `infras/rabbitmq/rabbitmq.conf` | AMQP/management/Prometheus listeners, heartbeat, memory and disk thresholds |
| RabbitMQ | `infras/rabbitmq/enabled_plugins` | Enables management and Prometheus plugins without a startup shell command |
| etcd | `infras/etcd/etcd.conf.yml` | Existing single-node identity, snapshots, hourly compaction, 4 GiB backend quota |
| Milvus | `infras/milvus/user.yaml` | Existing `by-dev` metadata root, etcd path defaults, MinIO protocol, health and logging overrides |

PostgreSQL, Redis, RabbitMQ, etcd, and Milvus keep their state in named volumes. Recreating their containers applies updated config without deleting those volumes. Milvus connection addresses, object-store credentials, and bucket name remain environment-driven in Compose and take precedence over matching defaults in `user.yaml`.

MinIO intentionally has no separate config file. Its standalone server path, console listener, credentials, and Prometheus access mode are concise environment/command settings in Compose.

## Networks

Compose uses two networks:

| Network | Purpose |
|---|---|
| `public` | Services that publish host ports: gateway and admin/debug UIs |
| `internal` | Application and infrastructure service-to-service traffic |

Services that need a host-bound admin UI and internal service traffic join both networks. Core protocols remain private through `expose`. 

*Note: The `internal` network is configured to allow outbound egress traffic so that containers like `backend` and `worker` can connect to external model APIs (such as local LLM servers or OpenAI), while keeping database and microservice ports unexposed to the host.*

## Gateway

`infras/nginx/nginx.conf` defines the public HTTP entrypoint.

Routes:

| Path | Behavior |
|---|---|
| `/health` | Gateway readiness response |
| `/api/` | Proxies to `backend:8000` |
| `/` | Proxies to `frontend:5173` |

The gateway forwards request context with `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Request-ID`.

API proxy reads and sends are allowed to run for up to `600` seconds. This keeps long-running chat responses, especially LLM-backed RAG answers, behind the same-origin `/api/` gateway path without prematurely closing the browser connection while the backend is still generating and persisting the answer.

### Dynamic DNS Resolution

To prevent stale DNS caching issues when service containers (like `frontend` or `backend`) are restarted or recreated (which changes their internal Docker network IP addresses), the gateway uses Docker's internal DNS resolver (`127.0.0.11` with a `valid=5s` TTL). 

Instead of referencing static `upstream` block names, Nginx variables (`$frontend_upstream`, `$backend_upstream`) are used within the `proxy_pass` directives. This forces Nginx to re-resolve the target container's IP dynamically at runtime using the resolver configuration.

## Storage And Buckets

MinIO stores binary objects. PostgreSQL remains the source of truth for business metadata when persistence is implemented.

There is no MinIO bootstrap container in the Compose stack. Bucket ownership is handled at the service boundary:

| Bucket | Owner |
|---|---|
| `${MINIO_BUCKET}` | Backend `ObjectStorageProvider` creates it lazily before writing meeting assets |
| `${MILVUS_BUCKET}` | Milvus receives the bucket name through `MINIO_BUCKET_NAME` and manages its own object-storage path |

Milvus now depends directly on the MinIO service healthcheck. It authenticates against MinIO with `MINIO_ACCESS_KEY_ID` and `MINIO_SECRET_ACCESS_KEY`.

## Monitoring

Prometheus runs as an internal monitoring service. Its UI is exposed only through `LOCAL_BIND_IP` for local operations. The frontend dashboard does not call Prometheus directly; it calls `GET /api/admin/metrics`, and the backend queries Prometheus through the internal network.

Current scrape jobs:

| Job | Target | Purpose |
|---|---|---|
| `prometheus` | `prometheus:9090` | Prometheus self health |
| `backend` | `backend:8000/metrics` | Backend HTTP, latency, meeting, job, and chat metrics |
| `docker` | `docker-exporter:9104/metrics` | `omnicall` Compose container CPU and memory metrics |
| `nginx` | `nginx-exporter:9113/metrics` | Gateway connection metrics from internal `stub_status` |
| `postgres` | `postgres-exporter:9187/metrics` | PostgreSQL health, connections, and activity |
| `redis` | `redis-exporter:9121/metrics` | Redis memory, command, keyspace, and connection metrics |
| `rabbitmq` | `rabbitmq:15692/metrics` | RabbitMQ queue, consumer, message, and node metrics |
| `minio` | `minio:9000/minio/v2/metrics/cluster` | MinIO cluster capacity and request metrics |
| `milvus` | `milvus:9091/metrics` | Milvus vector database metrics |
| `etcd` | `etcd:2379/metrics` | Milvus metadata store metrics |

The Docker stats exporter replaces the initial cAdvisor attempt for this local machine. cAdvisor was able to scrape host cgroups but could not resolve Docker container metadata with the active Docker storage layout, so it did not provide reliable per-service labels. The project exporter reads the Docker socket read-only, filters running containers by `com.docker.compose.project=omnicall`, and emits project container CPU cores and memory working-set gauges for Prometheus.

## Worker Runtime

The `worker` service uses the backend image and starts Celery with:

```bash
celery -A backend.configs.celery_app.celery_app worker --loglevel=INFO --queues=meeting-processing,processing-maintenance,chat-processing --concurrency=1 --hostname=worker@%h --without-gossip --without-mingle
```

The Compose command also includes the durable `chat-processing` queue. The worker consumes meeting processing, chat/memory, and maintenance tasks; it reloads authoritative business/job/turn/snapshot/feedback state from PostgreSQL and uses Redis only for temporary locks, cache, and operational events. Long processing/repair locks use token-checked heartbeat renewal. The separate `beat` service publishes reconciliation every 60 seconds. In addition to stale queued meetings, reconciliation recovers expired chat turns, stuck feedback-memory sync, stale memory revalidation, and pending/expired vector-repair claims.

`meeting-processing`, `processing-maintenance`, and `chat-processing` use separate durable direct exchanges/routing keys, and messages use persistent delivery. Meeting, chat, feedback-memory, and revalidation tasks use late acknowledgment/reject-on-worker-loss as appropriate, allowing RabbitMQ to redeliver interrupted work while PostgreSQL leases/revisions make execution idempotent. Celery remote control is enabled in the app config so backend admin deletion can revoke queued meeting-processing tasks by job ID. RabbitMQ 4 explicitly permits the deprecated transient non-exclusive pidbox queues still used by Celery 5.6 remote control. The Compose command still avoids gossip/mingle, and the worker healthcheck uses a targeted `celery inspect ping` so a live container with a stopped consumer is reported unhealthy.

## Runtime Configuration

The root `.env.example` follows the project ordering rule:

```text
bind IPs -> ports -> service credentials -> app config -> global
```

Docker Compose uses the root `.env` automatically when no explicit env file override is passed. If a stack was recreated with the template env file by mistake, the running containers keep those example values until they are recreated again with the intended root `.env`.

Backend and worker receive application resilience, Simple RAG stage budgets, LLM reasoning mode, and chat-turn lease configuration explicitly through Compose, in addition to `RATE_LIMIT_*`, `CONCURRENCY_LIMIT_*`, `TASK_LIMIT_*`, and `CIRCUIT_BREAKER_*`. Port-only variables such as `FRONTEND_PORT` and `BACKEND_PORT` remain template metadata because the local stack exposes the application through Nginx.

The key sets in `.env` and `.env.example` are kept identical. The root `.env` may override template values for a local endpoint, while `.env.example` contains safe development placeholders. Simple RAG deadlines and extraction-window limits are explicit in both files so direct backend runs and Compose runs use the same configuration surface. Settings validation rejects invalid reasoning/prompt modes, out-of-range limits, or a chat lease shorter than the longest guarded stage plus margin. Backend and Celery startup logs print only a non-secret effective summary.

Notable local defaults:

| Variable | Value | Reason |
|---|---|---|
| `NGINX_PORT` | `8080` | Public gateway port |
| `ADMINER_PORT` | `8081` | PostgreSQL admin UI port |
| `MINIO_CONSOLE_PORT` | `8082` | MinIO admin UI port |
| `MILVUS_WEBUI_PORT` | `8083` | Milvus built-in WebUI port, served from `/webui` |
| `REDIS_INSIGHT_PORT` | `8084` | RedisInsight admin UI port |
| `RABBITMQ_MANAGEMENT_PORT` | `8085` | RabbitMQ Management UI port |
| `PROCESSING_RECONCILIATION_INTERVAL_SECONDS` | `60` | Celery Beat interval for pending-job recovery |
| `PROCESSING_RECONCILIATION_STALE_SECONDS` | `120` | Minimum pending age before automatic republish |
| `PROCESSING_RECONCILIATION_BATCH_SIZE` | `100` | Maximum stale jobs recovered per cycle |
| `CHAT_TURN_LEASE_SECONDS` | `300` | Durable chat worker lease and stale-takeover fence |
| `RAG_QUERY_INTERPRETATION_TIMEOUT_SECONDS` | `15` | QuerySpec budget |
| `DEFAULT_CHAT_LANGUAGE` | `en` | Fallback chat locale when a client omits `language` |
| `RAG_EVIDENCE_RETRIEVAL_TIMEOUT_SECONDS` | `20` | Retrieval/EvidenceBundle budget |
| `RAG_SYNTHESIS_PRIMARY_TIMEOUT_SECONDS` / `FALLBACK_TIMEOUT_SECONDS` | `60` / `40` | Explicit provider budgets |
| `RAG_FINALIZATION_RESERVE_SECONDS` / `RAG_CHAT_TURN_TIMEOUT_SECONDS` | `15` / `150` | Finalization reserve and total deadline |
| `RAG_SYNTHESIS_CONTRACT_RETRIES` | `1` | Exactly one contract-only retry |
| `LLM_REASONING_MODE` | `disabled` | Disable Qwen hidden thinking |
| `LLM_PROMPT_DATA_POLICY` | `trusted` | `trusted` or request-scoped `redact` outbound prompt data |
| `PROMETHEUS_PORT` | `8086` | Prometheus UI port |
| `PROMETHEUS_URL` | `http://prometheus:9090` | Internal URL used by backend admin metrics |
| `ADMIN_METRICS_CACHE_KEY` | `admin:metrics:snapshot` | Redis key for the normalized admin dashboard payload |
| `ADMIN_METRICS_CACHE_TTL_SECONDS` | `10` | Admin metrics cache TTL |
| `OPERATIONAL_LOG_STREAM_KEY` | `admin:logs:operational` | Redis Stream used by temporary Admin processing/RAG logs |
| `OPERATIONAL_LOG_MAX_LENGTH` | `1000` | Approximate retained event limit |
| `OPERATIONAL_LOG_TTL_SECONDS` | `86400` | Sliding operational stream TTL |
| `OPERATIONAL_LOG_DEFAULT_TAIL` | `100` | Default Admin log tail size |
| `OLLAMA_PORT` | `11434` | Localhost-bound Ollama API port |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Lets backend/worker containers call the Compose Ollama service |
| `VAD_MIN_SPEECH_MS` | `300` | Minimum local VAD speech-region duration |
| `VAD_SILENCE_GAP_MS` | `500` | Silence gap merged into nearby local VAD speech regions |
| `VAD_ENERGY_THRESHOLD` | `0.012` | RMS threshold for local energy VAD |
| `ASR_TIMEOUT_SECONDS` | `120` | Minimum local ASR command timeout |
| `ASR_TIMEOUT_REALTIME_FACTOR` | `1.0` | Multiplies normalized audio duration to extend ASR/diarization subprocess timeouts for longer voice files |
| `ASR_MIN_SEGMENT_CONFIDENCE` | `0.1` | Minimum confidence for worker-retained ASR segments |
| `ASR_MAX_NO_SPEECH_PROBABILITY` | `0.6` | No-speech probability threshold for rejecting ASR segments |
| `LLM_PROVIDER` | `endpoint` | Selects API/private endpoint/Ollama provider path |
| `LLM_ENDPOINT_COMPATIBILITY` | `openai` | Selects OpenAI-compatible or custom JSON endpoint behavior |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Local Ollama text embedding model |
| `EMBEDDING_DIMENSIONS` | `768` | Expected local embedding vector size |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | Ollama embedding request timeout |
| `EMBEDDING_BATCH_SIZE` | `16` | Maximum chunk texts sent in one Ollama embedding request |
| `EMBEDDING_MAX_RETRIES` | `2` | Bounded retry count for transient embedding failures |
| `EMBEDDING_RETRY_BACKOFF_SECONDS` | `0.2` | Exponential retry backoff base for embedding requests |
| `EMBEDDING_CONTRACT_VERSION` | `v1` | Embedding contract identity stored with indexed chunks |
| `VECTOR_PROVIDER` | `milvus` | Enables Milvus REST vector index with PostgreSQL fallback |
| `RERANK_TOP_K` | `12` | Retrieval candidate count before rerank |
| `RERANK_OUTPUT_K` | `6` | Reranked output count returned to chat |
| `RERANK_TIMEOUT_SECONDS` | `30` | Local rerank command timeout |
| `GUARDRAIL_MODEL` | `llama-guard3:1b` | CPU-first local Ollama guardrail model |
| `GUARDRAIL_TIMEOUT_SECONDS` | `20` | Local Ollama guardrail request timeout |
| `GUARDRAIL_MAX_RETRIES` | `0` | Local guardrail retry count |
| `GUARDRAIL_INPUT_ENABLED` | `true` | Enables chat input guardrail |
| `GUARDRAIL_OUTPUT_ENABLED` | `true` | Enables assistant output guardrail |
| `GUARDRAIL_STRICT_MODE` | `false` | Provider errors fail closed (`blocked`) when true; otherwise fail open (`allowed` + `provider_error`) |
| `GUARDRAIL_PII_REDACTION_ENABLED` | `true` | Redact PII in the copy sent to the guardrail model |
| `MILVUS_HOST` | `milvus` | Internal Milvus REST host |
| `MILVUS_PORT` | `19530` | Internal Milvus REST port |
| `MILVUS_COLLECTION` | `meeting_chunks` | Milvus collection for derived meeting chunk vectors |
| `LLM_TIMEOUT_SECONDS` | `60` | LLM provider HTTP timeout |
| `LLM_MAX_RETRIES` | `1` | Retry count for retryable LLM provider failures |
| `LLM_RETRY_BACKOFF_SECONDS` | `0.2` | Linear retry backoff base for LLM provider calls |
| `OLLAMA_LLM_TIMEOUT_SECONDS` | `600` | Longer timeout for CPU-based local fallback analysis |
| `OLLAMA_CONTEXT_LENGTH` | `8192` | Ollama context window used by local LLM analysis |
| `OLLAMA_MAX_OUTPUT_TOKENS` | `1024` | Maximum tokens generated by one local fallback analysis call |
| `AUTH_SESSION_TTL_HOURS` | `168` | Local bearer-session lifetime used by backend auth |
| `UPLOAD_MAX_BYTES` | `524288000` | Backend upload size limit |
| `UPLOAD_ALLOWED_EXTENSIONS` | audio/video extensions | Backend upload extension allowlist |
| `UPLOAD_ALLOWED_CONTENT_TYPES` | audio/video MIME types | Backend upload content-type allowlist |
| `REDIS_PROCESSING_LOCK_TTL_SECONDS` | `900` | Meeting processing lock TTL used by workers |

## Docker Build Context

The root `.dockerignore` keeps generated JavaScript artifacts out of service build contexts:

```text
**/node_modules/
**/dist/
**/build/
**/*.tsbuildinfo
**/vite.config.d.ts
**/vite.config.js
```

This prevents local frontend installs and Vite output from being sent to Docker when rebuilding services. The frontend image build context was verified at `2.26kB` after these ignores were added.

Generated local runtime artifacts are disposable and stay outside the source tree: Python bytecode/cache directories, pytest/tool caches, frontend `dist` output, logs, temporary files, and local data are ignored and can be removed without touching application state. Docker named volumes are intentionally different: `postgres_data`, `minio_data`, `milvus_data`, `redis_data`, `rabbitmq_data`, `ollama_data`, `model_cache`, `etcd_data`, `prometheus_data`, and `redisinsight_data` contain runtime data and are preserved by routine cleanup. Use `docker compose down -v` only for an explicit disposable reset.

The backend image uses Python 3.11 and installs `ffmpeg`, `git`, `libsndfile`, `sox`, build tooling, CPU-only `torch/torchaudio`, `faster-whisper`, WeSpeaker, and SentenceTransformers dependencies. The same image is used by the API and worker containers so both can import provider code, while long-running voice processing still executes in the worker path. ffmpeg, `/models`, `/models/.hf-cache`, and `/tmp/omnicall-audio` are fixed image/runtime contracts rather than environment variables.

## Model Bootstrap

Compose has two one-shot model bootstrap services:

| Service | Writes to | Behavior |
|---|---|---|
| `ollama-init` | `ollama_data:/root/.ollama` through the running `ollama` service | Pulls `OLLAMA_MODEL`, `EMBEDDING_MODEL`, and `GUARDRAIL_MODEL` with `ollama pull` |
| `model-init` | `model_cache:/models` | Downloads the repository-defined ASR, diarization, and rerank Hugging Face snapshots |

`backend` and `worker` mount `model_cache` at `/models` and wait for both init services to complete. This means `docker compose up` prepares model files before app services start. Ollama bootstrap derives its pull list directly from the three configured runtime model names, so there is no second list to keep synchronized. Specialized ASR, diarization, and rerank sources are versioned with `model-init`; changing them requires a coordinated code/image change instead of an unchecked `.env` override.

Default specialized local models are stored in the `model_cache` named volume:

| Path in container | Default source | Used by |
|---|---|---|
| `/models/asr` | `Systran/faster-whisper-medium` | `backend.model_runners.asr` |
| `/models/diarization` | `Wespeaker/wespeaker-voxceleb-resnet34-LM` | `backend.model_runners.diarization` |
| `/models/rerank` | `BAAI/bge-reranker-v2-m3` | `backend.model_runners.rerank` |
| `/models/.hf-cache` | Hugging Face cache files | Snapshot reuse across bootstrap runs |

## Verification

Commands used for Phase 2 verification:

```bash
docker compose config
docker compose up -d --build
docker compose exec -T backend alembic upgrade head
docker compose ps -a
curl http://127.0.0.1:8080/api/health
```

Verified host HTTP endpoints:

| Endpoint | Status |
|---|---|
| `http://127.0.0.1:8080/api/health` | `200` |
| `http://127.0.0.1:8080/` | `200` |
| `http://127.0.0.1:8081/` | `200` |
| `http://127.0.0.1:8082/` | `200` |
| `http://127.0.0.1:8083/webui` | `200` |
| `http://127.0.0.1:8084/` | `200` |
| `http://127.0.0.1:8085/` | `200` |
| `http://127.0.0.1:8086/-/healthy` | `200` |

Phase 3 backend verification also confirmed:

| Check | Result |
|---|---|
| Alembic baseline migration | Applied |
| Meeting create/upload/process/status through gateway | Passed |
| PostgreSQL metadata counts for meeting, asset, job | Present |
| RabbitMQ `meeting-processing` queue | Received one ready message |
| Unauthorized meeting list without auth headers | `401` |
| Frontend build with `npm run build` | Passed |
| Playwright desktop/mobile screenshots | Passed |
| Playwright UI smoke create/upload/process flow | Passed |

Phase 4 worker slice verification also confirmed:

| Check | Result |
|---|---|
| Compose config after worker changes | Passed |
| Backend syntax compile | Passed |
| Alembic current revision | `0003_intel_indexes (head)` |
| Backend, worker, and NGINX services | Healthy |
| Gateway `GET /api/health` | `200` |
| Uploaded `.wav` meeting queued through RabbitMQ/Celery without configured local ASR/LLM models | Job fails safely and remains retryable |
| Processing service with test-only model fixtures | Persists `meeting-intelligence-result.v2`, transcript, knowledge, evidence, and chunk rows |
| LLM provider selection and fallback tests | Passed |
| LLM analysis merge and provider failure tests | Passed |
| Worker idempotency, lock, and provider-failure state tests | Passed |
| Text transcript extraction and text-upload processing tests | Passed |
| Derived transcript/insight index persistence tests | Passed |
| Provider retry and worker `RETRYING` tests | Passed |
| Backend `unittest` suite after model-provider standardization | 54 tests passed |

Phase 5 retrieval indexing slice verification also confirmed:

| Check | Result |
|---|---|
| Compose config after embedding env wiring | Passed |
| Backend syntax compile | Passed |
| Alembic current revision | `0004_meeting_chunks (head)` |
| Backend, worker, and NGINX services | Healthy |
| Gateway `GET /api/health` | `200` |
| Retrieval chunk builder and deterministic embedding tests | Passed |
| Backend `unittest` suite after retrieval indexing slice | 23 tests passed |

Phase 5 chat backend slice verification also confirmed:

| Check | Result |
|---|---|
| Alembic current revision | `0005_chat_history (head)` |
| Backend, worker, and NGINX services | Healthy |
| Gateway `GET /api/health` | `200` |
| Chat persistence, authorization, citations, no-evidence, and LLM-failure fallback tests | Passed |
| Backend `unittest` suite after chat backend slice | 27 tests passed |

Phase 5 Milvus retrieval slice verification also confirmed:

| Check | Result |
|---|---|
| Milvus service | Healthy |
| Worker retrieval vector upsert through Milvus REST | `status=upserted` |
| Retrieval search through Milvus with PostgreSQL record reload | Returned authorized `meeting_chunks` |
| Vector-provider failure fallback to PostgreSQL ranking | Passed |
| Backend `unittest` suite after Milvus retrieval slice | 29 tests passed |

Phase 5 frontend chat UI verification also confirmed:

| Check | Result |
|---|---|
| Frontend TypeScript/Vite build after chat tab wiring | Passed |
| Frontend Docker image build after `.dockerignore` update | Passed |
| Frontend Docker build context after generated artifact ignores | `2.26kB` |
| Gateway `GET /` after frontend and NGINX recreate | `200` |
| Frontend, backend, and NGINX services | Healthy |

Phase 5 completion verification also confirmed:

| Check | Result |
|---|---|
| Backend and worker images rebuilt after evidence guard changes | Passed |
| Backend `unittest` suite after evidence guard | 30 tests passed |
| Gateway `GET /api/health` after backend/NGINX recreate | `200` |
| Manual voice upload, processing, chunk indexing, and chat through gateway | Passed |
| Action item, timeline, risk, and important-note questions | Returned meeting citations |
| Unrelated Bitcoin question | Returned `not_enough_evidence` with no citations |
| Citation mapping against processed JSON transcript/analysis pointers | Passed |

Phase 5.5 foundation verification also confirmed:

| Check | Result |
|---|---|
| Compose config after voice/rerank env wiring | Passed |
| Backend and worker images rebuilt after provider contract, ffmpeg, voice warning, and ASR adapter changes | Passed |
| Targeted retrieval/chat/transcription/voice provider tests | Passed |
| Local WAV metadata fallback, energy VAD, ASR failure, local command ASR, local-only ASR selection, diarization command, and voice warning tests | Passed |
| Rerank command and unavailable-command tests | Passed |
| Gateway `GET /api/health` after backend/worker/NGINX recreate | `200` |
| Backend `unittest` suite after Phase 5.5/model-provider standardization | 54 tests passed |

Phase 5.6 guardrail verification also confirmed:

| Check | Result |
|---|---|
| Compose config after guardrail env wiring | Passed |
| Backend and worker images rebuilt after guardrail provider/service changes | Passed |
| Targeted guardrail provider and chat guardrail tests | Passed |
| Compose Ollama runtime check | Service healthy on `127.0.0.1:11434` and internal `ollama:11434` |
| `model-init` dry-run without downloads | Passed |
| `ollama-init` dry-run without model list | Passed |
| Backend `unittest` suite after model-provider standardization | 54 tests passed |

Phase 5.5 and 5.6 end-to-end voice/RAG verification also confirmed:

| Check | Result |
|---|---|
| Backend and worker images rebuilt with Python 3.11 CPU model runtime dependencies | Passed |
| `model-init` populated ASR, diarization, and rerank snapshots in `model_cache` | Passed |
| ASR runner smoke test over MP3 | Produced real transcript segments |
| WeSpeaker diarization runner smoke test over normalized WAV | Produced speaker assignments |
| Rerank runner smoke test | Returned ranked chunk IDs |
| Voice MP3 upload through gateway | Meeting processed to `READY`, job `SUCCEEDED` |
| Processed JSON source metadata | Recorded local ASR, WeSpeaker diarization, ffmpeg preprocessing, and voice metadata |
| Milvus collection dimension mismatch handling | Dropped/recreated incompatible collection and upserted 3 chunks |
| Chat over the processed voice meeting | HTTP `200`, grounded answer, citations, rerank metadata, and input/context/output guardrail `allow` metadata |
| Current Compose service health | Backend, worker, gateway, PostgreSQL, Redis, RabbitMQ, MinIO, Milvus, Ollama, and admin UIs healthy |

Phase 6 admin and operations verification also confirmed:

| Check | Result |
|---|---|
| Compose config after monitoring/exporter wiring | Passed |
| Backend image rebuilt after admin metrics query changes | Passed |
| Backend admin metrics unit tests | 2 tests passed |
| Backend syntax compile | Passed |
| Frontend TypeScript/Vite build after admin dashboard wiring | Passed |
| Docker stats exporter direct scrape | Returned `omnicall_docker_container_*` metrics in about 3.8 seconds |
| Prometheus active targets | 10 total, 10 up |
| Admin API without auth | `401 missing_auth_context` |
| Admin API with admin headers | `summary.status=healthy`, `10/10` targets healthy |
| Redis admin metrics cache | First request `cache.hit=false`, immediate second request `cache.hit=true`; admin meeting/account deletion invalidates the snapshot |
| Container metrics in admin response | `container_cpu` and `container_memory` query all `omnicall` Compose containers |
| Infrastructure metrics in admin response | PostgreSQL connection-state/size, Redis memory/clients, RabbitMQ queue/consumer, MinIO capacity/usage, etcd DB size, Milvus request/collection/row, and NGINX connection series returned successfully |

Phase 7 hardening verification also confirmed:

| Check | Result |
|---|---|
| Compose config after auth/session env wiring | Passed |
| Alembic current revision | `0007_normalize_product_roles (head)` |
| Current Compose service health | Backend, worker, frontend, gateway, PostgreSQL, Redis, RabbitMQ, MinIO, Milvus, Prometheus, Ollama, and admin/debug UIs running; backend/worker healthy |
| Gateway smoke for auth, files, admin metrics, and admin meeting deletion | Passed |
| External infrastructure config mounts | PostgreSQL, Redis, RabbitMQ, etcd, and Milvus configs mounted read-only |
| Stateful service recreation | All five services healthy with existing named volumes preserved |
| PostgreSQL config/HBA | Custom config loaded; Docker client authenticated with SCRAM |
| Redis config | AOF enabled, `maxmemory=512mb`, `noeviction`, protected mode enabled |
| RabbitMQ plugins | Management and Prometheus plugins enabled from `enabled_plugins` |
| Celery Beat reconciliation | Automatically published after 60 seconds and completed on the isolated `processing-maintenance` queue |
| RabbitMQ application queues | `meeting-processing` and `processing-maintenance` durable with independent direct exchange/routing-key bindings |
| Full backend suite after reconciliation hardening | 82 tests passed |
| etcd persistence | Existing member ID and 3.3 MB database retained; hourly compaction and 4 GiB quota active |
| Milvus persistence | `meeting_chunks` collection remained available after config-mounted recreation |

Phase 8 operational-log verification on 2026-06-19 also confirmed:

| Check | Result |
|---|---|
| Redis operational Stream | Structured event present with meeting, file, job, provider/model, duration, and details |
| Stream retention | `MAXLEN ~ 1000`, sliding TTL approximately 24 hours |
| Admin logs gateway API | Admin `200`; User `403 admin_access_required` |
| Clear behavior | Admin clear returned `200` and the subsequent tail contained zero events |
| Runtime health | Backend, worker, frontend, NGINX, and Redis healthy |

For local development after retrieval chunk format changes, rebuild derived retrieval data from the backend environment:

```bash
python -m backend.scripts.rebuild_retrieval_index --clear-chat
```

The command reuses backend settings, reads stored `meeting_intelligence_results`, replaces PostgreSQL `meeting_chunks`, assigns an index generation, upserts fresh Milvus vectors, and optionally clears chat messages that may cite stale chunk IDs. The PostgreSQL trigram fallback index is created by the retrieval migration. Phase 22 rebuilds only the RAG-first intelligence schema; obsolete local JSON documents from the previous `summary`/`analysis`/`citations` contract are rejected and must be reprocessed or removed. Use `--meeting-id <id>` to rebuild one meeting. When preserving local data is not useful, `docker compose down -v` followed by stack startup, migrations, and reprocessing remains the clean-slate path; it deletes local PostgreSQL, Redis, RabbitMQ, MinIO, Milvus, and model/runtime volumes.

MinIO object cleanup is available through `python -m backend.scripts.cleanup_orphaned_objects`. It compares bucket objects with PostgreSQL `meeting_assets.object_key`, reports orphaned objects by default, and requires `--apply` for deletion. This is the recovery path for objects left behind by interrupted or older cleanup flows.

Phase 6 runtime verification also confirmed:

| Check | Result |
|---|---|
| `docker compose config --quiet` | Passed |
| `.env` and `.env.example` key sets | Identical; no duplicate keys, including retrieval, extraction-window, and Agentic RAG limits |
| Gateway health | `GET /api/health` returned `{"app":"Omnicall API","status":"ok"}` |
| Milvus WebUI | Port `8083` reachable and redirected to `/webui/` |
| Frontend production build | `tsc -b && vite build` passed |
| Backend unittest discovery | `225` tests passed |

The final Docker/Compose cleanup audit found no unused service or volume declaration across the `21` declared services: application dependencies, Milvus/etcd/MinIO storage, model bootstrap services, local admin UIs, and Prometheus exporters are all referenced by the runtime topology. The repository now contains only the two active backend maintenance commands, `rebuild_retrieval_index` and `cleanup_orphaned_objects`; generated Python and frontend artifacts were removed from the workspace after verification.

| Extraction window target tokens | `EXTRACTION_WINDOW_TARGET_TOKENS` | `2000` | Target input size for bounded LLM extraction windows |
| Extraction window hard limit | `EXTRACTION_WINDOW_HARD_LIMIT_TOKENS` | `2800` | Hard prompt window limit before a new window is started |
| Extraction window overlap | `EXTRACTION_WINDOW_OVERLAP_SEGMENTS` | `1` | Number of previous speaker turns retained as overlap |
| Extraction window workers | `EXTRACTION_WINDOW_MAX_WORKERS` | `4` | Maximum bounded parallel local extraction calls |

Phase 25 adds the `meeting_transcript_windows` PostgreSQL table. It stores window references and local extraction state; it does not replace the full transcript and is not written directly to Milvus. Retrieval chunks remain authoritative in PostgreSQL and their derived vectors remain generation-validated in Milvus.

The durable PostgreSQL orchestration schema is now bootstrapped from the single `0001_initial_schema` baseline. It creates the core business tables for users, sessions, audit events, meetings, assets, transcript windows, intelligence results, retrieval chunks, chat messages, chat turns, retrieval snapshots, and feedback, plus the `pg_trgm` extension for retrieval fallback. Chat broker publication can fail without losing the queued turn; turnaround leases and vector-repair claims retain retry intent for reconciliation.

Redis holds only disposable Cache v2 artifacts and coordination state. Embedding, retrieval-ID, and verified-answer entries are isolated by owner, meeting, index generation, canonical/context signature, and pipeline fingerprint. Retrieval/answer hits rehydrate PostgreSQL chunks/citations and validate integrity/generation before serving. Exact lookup does not depend on embeddings; Redis failure is fail-open. Answer entries use a 24-hour base TTL, thumbs-up promotion uses seven days, and the meeting-local index is atomically bounded to 100 entries. Semantic scans keep valid entries for different context fingerprints side by side: an incompatible context is skipped without removing the other entry, while stale generation/pipeline or corrupt-integrity entries are pruned. Reindex/reprocess/delete/feedback lifecycle changes establish logical invalidation in PostgreSQL or generation state first; physical Redis cleanup happens best-effort after commit.

Semantic cache is deliberately configured as `shadow` with threshold `0.94` and canary `0%`. Direct serving requires a verified entry, compatible operation/target/shape/branch/entity/relation/filter/negation/time/locale/context features, observed precision of at least `0.99`, and deterministic canary membership. Operators can switch `canary -> shadow -> off` through environment configuration without changing durable data.

Redis also owns token-checked processing locks, answer singleflight keys, transient SSE Pub/Sub, and bounded operational logs; none are business truth. RabbitMQ delivers durable work but PostgreSQL rows/revisions/leases provide idempotency and recovery. Milvus continues to store rebuildable vectors only, and every vector result is fenced by the PostgreSQL retrieval snapshot generation.

Phase 46 adds no durable table or migration. Validated Semantic Query IR frames and exact-adjacent clarification-repair frames use the existing `chat_messages.metadata_json` JSONB boundary. PostgreSQL therefore remains authoritative for continuation and repair; Redis is not their source of truth. The backend accepts only closed internal metadata contracts, anchors inherited frames to durable message IDs, and omits `semanticQuery`, `semanticQueryGraph`, `clarificationRepair`, and semantic grounding details from the public chat metadata allowlist. The same surface follow-up under different validated semantic frames receives a different context fingerprint and cannot share contextual cache identity. A fully covered digit-bound participant collection remains standalone and cannot be rebound to a historical entity; meeting-global participant lists use exact aggregate plus complete-roster evidence, while scoped/unsupported aggregate contracts fail closed.

Phase 47 also adds no durable table or migration. Eligible completed assistant messages persist the validated internal `semanticQueryGraph` in the same `chat_messages.metadata_json`; each request rebuilds bounded `DiscourseState` focus from those graphs and exact durable user/assistant message anchors. There is no discourse row, Redis session object, new queue, service, or volume. Assistant prose remains untrusted and is excluded from focus/evidence. PostgreSQL continues to own completed turns, graph metadata, retrieval snapshots, and meeting evidence; Redis remains disposable cache/coordination, RabbitMQ remains delivery, and Milvus remains a generation-validated derived vector index.

The QueryGraph cache payload canonicalizes answer-affecting goal order/topology, Query IR, detail, concepts, proposition, and reference semantics while excluding provider-generated IDs, confidence, historical focus IDs, and provenance-only source spans. Historical focus remains isolated through the separate context fingerprint and exact message anchors. The current pipeline uses `meeting-tools.v7-evidence-facets`, `conversation-resolver.v14-role-bound-history-context`, `semantic-query.v7-open-contact-facets`, `meeting-query-graph.v11-trusted-history-focus-materialization`, `capability-query-plan.v7-graph-branches`, `hybrid-rrf.v3-branch-coverage-facets`, `claim-synthesis.v21-proposition-schema-example`, `claim-evidence.v11-scoped-semantic-fallback-sensitive-fields`, and output guardrail prompt `v6-typed-contact-verification-mode`. Cache and Agent Memory compatibility also includes canonical graph/branch semantics, entities, relations, typed filters, negation, time, and trusted context, so contract changes invalidate old derived identities without converting Redis into business state.

The S7 output-policy exception is evidence-aware rather than a blanket PII bypass. It requires an owner-authorized meeting request, the exact typed requested phone/email/address field, grounded state, citations, passed claim verification, and verified current-snapshot evidence refs. Credentials, payment-card data, government identifiers, unrequested contact types, cross-field disclosure, and unverified answers remain blocked. Generated and cached answers use the same recheck metadata.

Milvus and PostgreSQL candidates are merged with reciprocal-rank fusion; PostgreSQL remains the source rehydrated for final chunks and citations. Validated Query IR requests apply authoritative source pins and do not block on a per-request local crossencoder. Legacy surface-only requests may still rerank, but subprocess timeout is converted to a typed provider error and falls back to fused order. Parallel batches receive only the remaining total Agent deadline, and timeout/failure paths return bounded partial or not-enough-evidence results through the same claim gate rather than retrying every failed tool without a bound.

*Document reflects project state at **Phase 47 Query Graph Discourse and Evidence Branch Architecture (In Progress)**. Phase 46 remains the completed semantic/cardinality baseline. PostgreSQL is authoritative for meeting evidence, completed-turn graph lineage, retrieval snapshots, and clarification repair; Redis is fail-open context-safe cache/coordination, RabbitMQ is delivery, and Milvus is a generation-validated derived index. The RAG pipeline contract is `v4` (retrieval remains `v3`) so answer-cache and memory entries created before mandatory LLM-origin synthesis are incompatible; no durable schema is added.*
