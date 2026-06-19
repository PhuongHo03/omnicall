# Infrastructure Explanation

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
| `worker` | Celery meeting processing worker | Internal only, no host ports |
| `beat` | Celery periodic reconciliation scheduler | Internal only, no host ports |
| `postgres` | Durable relational state | Internal only, `expose: 5432` |
| `redis` | Cache, locks, idempotency, short-lived snapshots, bounded operational event stream | Internal only, `expose: 6379` |
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
celery -A backend.configs.celery_app.celery_app worker --queues=meeting-processing,processing-maintenance --concurrency=1 --without-gossip --without-mingle
```

The worker consumes processing and maintenance tasks, loads authoritative meeting/job/asset state from PostgreSQL, uses Redis locks for meeting-level idempotency, writes processed JSON back to PostgreSQL, and updates job/meeting status. The separate `beat` service publishes reconciliation every 60 seconds. Jobs still `PENDING` with meetings still `QUEUED` after 120 seconds are republished with their original IDs.

The `meeting-processing` and `processing-maintenance` queues use separate durable direct exchanges/routing keys, and messages use persistent delivery. Meeting-processing tasks use late acknowledgment and reject-on-worker-loss, allowing RabbitMQ to redeliver interrupted work. Celery remote control is enabled in the app config so backend admin deletion can revoke queued meeting-processing tasks by job ID. RabbitMQ 4 explicitly permits the deprecated transient non-exclusive pidbox queues still used by Celery 5.6 remote control. The Compose command still avoids gossip/mingle, and the worker healthcheck uses a targeted `celery inspect ping` so a live container with a stopped consumer is reported unhealthy.

## Runtime Configuration

The root `.env.example` follows the project ordering rule:

```text
bind IPs -> ports -> service credentials -> app config -> global
```

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
| `OLLAMA_BOOTSTRAP_MODELS` | `qwen2.5:1.5b nomic-embed-text llama-guard3:1b` | Models pulled by `ollama-init` into `ollama_data` |
| `MODEL_CACHE_DIR` | `/models` | Mount point for the `model_cache` volume in backend, worker, and `model-init` |
| `HF_HOME` | `/models/.hf-cache` | Hugging Face cache directory inside `model_cache` |
| `VOICE_FFMPEG_PATH` | `ffmpeg` | ffmpeg executable used by backend/worker voice preprocessing |
| `VOICE_WORK_DIR` | `/tmp/omnicall-audio` | Container-local directory for derived temporary audio files |
| `VAD_MIN_SPEECH_MS` | `300` | Minimum local VAD speech-region duration |
| `VAD_SILENCE_GAP_MS` | `500` | Silence gap merged into nearby local VAD speech regions |
| `VAD_ENERGY_THRESHOLD` | `0.012` | RMS threshold for local energy VAD |
| `ASR_MODEL` | `whisper-small-int8` | CPU-friendly local ASR model identifier |
| `ASR_COMPUTE_TYPE` | `int8` | Local ASR compute mode |
| `ASR_COMMAND` | `python -m backend.model_runners.asr --audio-path {audio_path} --model-dir {model_cache_dir}/asr --model-name {model} --compute-type {compute_type}` | Local faster-whisper ASR command template |
| `ASR_HF_REPO` | `Systran/faster-whisper-small` | Model repo downloaded by `model-init` into `/models/asr` |
| `ASR_HF_REVISION` | `main` | ASR model revision downloaded by `model-init` |
| `ASR_DOWNLOAD_COMMAND` | empty | Optional custom ASR download command; receives `MODEL_TARGET_DIR` |
| `ASR_TIMEOUT_SECONDS` | `120` | Minimum local ASR command timeout |
| `ASR_TIMEOUT_REALTIME_FACTOR` | `1.0` | Multiplies normalized audio duration to extend ASR/diarization subprocess timeouts for longer voice files |
| `DIARIZATION_MODEL` | `wespeaker-voxceleb-resnet34` | WeSpeaker-oriented local diarization model identifier |
| `DIARIZATION_COMMAND` | `python -m backend.model_runners.diarization --audio-path {audio_path} --model-dir {model_cache_dir}/diarization --device cpu` | Local WeSpeaker diarization command template |
| `DIARIZATION_HF_REPO` | `Wespeaker/wespeaker-voxceleb-resnet34-LM` | Model repo downloaded by `model-init` into `/models/diarization` |
| `DIARIZATION_HF_REVISION` | `main` | Diarization model revision downloaded by `model-init` |
| `DIARIZATION_DOWNLOAD_COMMAND` | empty | Optional custom diarization download command; receives `MODEL_TARGET_DIR` |
| `LLM_PROVIDER` | `endpoint` | Selects API/private endpoint/Ollama provider path |
| `LLM_ENDPOINT_COMPATIBILITY` | `openai` | Selects OpenAI-compatible or custom JSON endpoint behavior |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Local Ollama text embedding model |
| `EMBEDDING_DIMENSIONS` | `768` | Expected local embedding vector size |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | Ollama embedding request timeout |
| `VECTOR_PROVIDER` | `milvus` | Enables Milvus REST vector index with PostgreSQL fallback |
| `RERANK_MODEL` | `bge-reranker-v2-m3` | Local reranker model identifier |
| `RERANK_COMMAND` | `python -m backend.model_runners.rerank --model-dir {model_cache_dir}/rerank --model-name {model}` | Local SentenceTransformers cross-encoder rerank command template |
| `RERANK_HF_REPO` | `BAAI/bge-reranker-v2-m3` | Model repo downloaded by `model-init` into `/models/rerank` |
| `RERANK_HF_REVISION` | `main` | Rerank model revision downloaded by `model-init` |
| `RERANK_DOWNLOAD_COMMAND` | empty | Optional custom rerank download command; receives `MODEL_TARGET_DIR` |
| `RERANK_TOP_K` | `12` | Retrieval candidate count before rerank |
| `RERANK_OUTPUT_K` | `6` | Reranked output count returned to chat |
| `RERANK_TIMEOUT_SECONDS` | `30` | Local rerank command timeout |
| `GUARDRAIL_MODEL` | `llama-guard3:1b` | CPU-first local Ollama guardrail model |
| `GUARDRAIL_TIMEOUT_SECONDS` | `20` | Local Ollama guardrail request timeout |
| `GUARDRAIL_MAX_RETRIES` | `0` | Local guardrail retry count |
| `GUARDRAIL_INPUT_ENABLED` | `true` | Enables chat input guardrail |
| `GUARDRAIL_TRANSCRIPT_ENABLED` | `true` | Enables worker transcript guardrail |
| `GUARDRAIL_CONTEXT_ENABLED` | `true` | Enables retrieved context guardrail |
| `GUARDRAIL_OUTPUT_ENABLED` | `true` | Enables assistant output guardrail |
| `GUARDRAIL_STRICT_MODE` | `false` | Keeps local development fail-open with warnings when Ollama is unavailable |
| `MILVUS_HOST` | `milvus` | Internal Milvus REST host |
| `MILVUS_PORT` | `19530` | Internal Milvus REST port |
| `MILVUS_COLLECTION` | `meeting_chunks` | Milvus collection for derived meeting chunk vectors |
| `LLM_TIMEOUT_SECONDS` | `60` | LLM provider HTTP timeout |
| `LLM_MAX_RETRIES` | `1` | Retry count for retryable LLM provider failures |
| `LLM_RETRY_BACKOFF_SECONDS` | `0.2` | Linear retry backoff base for LLM provider calls |
| `OLLAMA_LLM_TIMEOUT_SECONDS` | `600` | Longer timeout for CPU-based local fallback analysis |
| `OLLAMA_CONTEXT_LENGTH` | `8192` | Ollama context window used by local LLM analysis |
| `AUTH_SESSION_TTL_HOURS` | `168` | Local bearer-session lifetime used by backend auth |
| `UPLOAD_MAX_BYTES` | `524288000` | Backend upload size limit |
| `UPLOAD_ALLOWED_EXTENSIONS` | audio/video/text transcript extensions | Backend upload extension allowlist |
| `UPLOAD_ALLOWED_CONTENT_TYPES` | audio/video/text transcript MIME types | Backend upload content-type allowlist |
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

The backend image uses Python 3.11 and installs `ffmpeg`, `git`, `libsndfile`, `sox`, build tooling, CPU-only `torch/torchaudio`, `faster-whisper`, WeSpeaker, and SentenceTransformers dependencies. The same image is used by the API and worker containers so both can import provider code, while long-running voice processing still executes in the worker path. Compose passes `VOICE_FFMPEG_PATH` so local builds can point to a different binary path if needed.

## Model Bootstrap

Compose has two one-shot model bootstrap services:

| Service | Writes to | Behavior |
|---|---|---|
| `ollama-init` | `ollama_data:/root/.ollama` through the running `ollama` service | Pulls every model listed in `OLLAMA_BOOTSTRAP_MODELS` with `ollama pull` |
| `model-init` | `model_cache:/models` | Downloads ASR, diarization, and rerank Hugging Face snapshots, or runs custom `*_DOWNLOAD_COMMAND` values |

`backend` and `worker` mount `model_cache` at `MODEL_CACHE_DIR` and wait for both init services to complete. This means `docker compose up` prepares model files before app services start. Compose uses default model values only when the related env variable is unset; an explicitly empty value means "skip." To skip Ollama pulls, set `OLLAMA_BOOTSTRAP_MODELS` to empty. To skip a specialized model download, set the matching `*_HF_REPO` and `*_DOWNLOAD_COMMAND` to empty. To replace the default source, set a custom `ASR_DOWNLOAD_COMMAND`, `DIARIZATION_DOWNLOAD_COMMAND`, or `RERANK_DOWNLOAD_COMMAND`; the command receives `MODEL_CACHE_DIR` and `MODEL_TARGET_DIR`.

Default specialized local models are stored in the `model_cache` named volume:

| Path in container | Default source | Used by |
|---|---|---|
| `/models/asr` | `Systran/faster-whisper-small` | `backend.model_runners.asr` |
| `/models/diarization` | `Wespeaker/wespeaker-voxceleb-resnet34-LM` | `backend.model_runners.diarization` |
| `/models/rerank` | `BAAI/bge-reranker-v2-m3` | `backend.model_runners.rerank` |
| `/models/.hf-cache` | Hugging Face cache files | Snapshot reuse across bootstrap runs |

## Verification

Commands used for Phase 2 verification:

```bash
docker compose --env-file .env.example config
docker compose --env-file .env.example up -d --build
docker compose --env-file .env.example exec -T backend alembic upgrade head
docker compose --env-file .env.example ps -a
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
| Processing service with test-only model fixtures | Persists `meeting-intelligence-result.v1`, transcript, insight, and chunk rows |
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
| Manual text transcript upload, processing, chunk indexing, and chat through gateway | Passed |
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
| Targeted guardrail provider, chat guardrail, and transcript guardrail tests | Passed |
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
| Processed JSON source metadata | Recorded local ASR, WeSpeaker diarization, ffmpeg preprocessing, transcript guardrail warning, and voice metadata |
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

*Document reflects project state after Phase 8 operational-log verification on **2026-06-19**. Redis additionally owns the bounded, expiring `admin:logs:operational` Stream consumed through Admin backend APIs; no new database or infrastructure service was added. The previously documented Phase 7 Compose stack remains wired and healthy.*
