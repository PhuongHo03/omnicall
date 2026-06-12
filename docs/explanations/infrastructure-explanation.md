# Infrastructure Explanation

## Structure

```text
.
├── .dockerignore                    <- Docker build context ignores for local artifacts
├── .env.example                    <- Runtime configuration template for Compose
├── docker-compose.yml              <- Local stack wiring, networks, volumes, healthchecks
└── infras/
    ├── nginx/
    │   └── nginx.conf              <- Public gateway routing
    └── prometheus/
        └── prometheus.yml          <- Internal Prometheus scrape config
```

## Runtime Services

The local runtime is managed through Docker Compose.

| Service | Role | Host Exposure |
|---|---|---|
| `nginx` | Public edge gateway | `${APP_BIND_IP}:${NGINX_PORT}:80` |
| `frontend` | Vite React UI | Internal only, `expose: 5173` |
| `backend` | FastAPI API server | Internal only, `expose: 8000` |
| `worker` | Celery meeting processing worker | Internal only, no host ports |
| `postgres` | Durable relational state | Internal only, `expose: 5432` |
| `redis` | Cache, locks, idempotency, short-lived snapshots | Internal only, `expose: 6379` |
| `rabbitmq` | Celery broker | AMQP internal, management UI on `${LOCAL_BIND_IP}:${RABBITMQ_MANAGEMENT_PORT}` |
| `minio` | Object storage for meeting assets and Milvus objects | API internal, console on `${LOCAL_BIND_IP}:${MINIO_CONSOLE_PORT}` |
| `minio-init` | Creates required MinIO buckets | One-shot internal task |
| `etcd` | Milvus metadata dependency | Internal only, `expose: 2379` |
| `milvus` | Vector database for meeting chunks | Internal only, `expose: 19530` and `9091` |
| `prometheus` | Internal metrics scraper | UI on `${LOCAL_BIND_IP}:${PROMETHEUS_PORT}` |
| `adminer` | Local database admin UI | `${LOCAL_BIND_IP}:${ADMINER_PORT}` |
| `redisinsight` | Local Redis admin UI | `${LOCAL_BIND_IP}:${REDIS_INSIGHT_PORT}` |

Only NGINX is public by default. Admin/debug UIs are localhost-bound through `LOCAL_BIND_IP`. Backend and infrastructure service protocols stay internal.

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

`minio-init` creates:

| Bucket | Purpose |
|---|---|
| `${MINIO_BUCKET}` | Omnicall meeting assets |
| `${MILVUS_BUCKET}` | Milvus object storage |

Milvus authenticates against MinIO with `MINIO_ACCESS_KEY_ID` and `MINIO_SECRET_ACCESS_KEY`.

## Monitoring

Prometheus runs as an internal monitoring service. Its UI is exposed only through `LOCAL_BIND_IP` for local operations.

Current scrape jobs:

| Job | Target |
|---|---|
| `prometheus` | `prometheus:9090` |

Backend scraping is intentionally commented out until `/metrics` exists.

## Worker Runtime

The `worker` service uses the backend image and starts Celery with:

```bash
celery -A backend.configs.celery_app.celery_app worker --queues=meeting-processing --concurrency=1 --without-gossip --without-mingle
```

The worker consumes RabbitMQ tasks from `meeting-processing`, loads authoritative meeting/job/asset state from PostgreSQL, uses Redis locks for meeting-level idempotency, writes processed JSON back to PostgreSQL, and updates job/meeting status.

Celery remote control is disabled in the app config and the Compose command avoids gossip/mingle. This local setup is intentional for RabbitMQ 4 compatibility because remote-control pidbox transient queues can be rejected by the broker. The worker healthcheck verifies RabbitMQ socket connectivity instead of using `celery inspect ping`.

## Runtime Configuration

The root `.env.example` follows the project ordering rule:

```text
bind IPs -> ports -> service credentials -> app config -> global
```

Notable local defaults:

| Variable | Value | Reason |
|---|---|---|
| `NGINX_PORT` | `8080` | Public gateway port |
| `PROMETHEUS_PORT` | `9096` | Avoids an occupied local `9090` |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Lets backend containers call a host Ollama service |
| `ANALYSIS_PROVIDER` | `local` | Keeps local processing deterministic by default; set `llm` to enable LLM-backed analysis with fallback |
| `LLM_PROVIDER` | `endpoint` | Selects API/private endpoint/Ollama provider path |
| `LLM_ENDPOINT_COMPATIBILITY` | `openai` | Selects OpenAI-compatible or custom JSON endpoint behavior |
| `EMBEDDING_DIMENSIONS` | `64` | Local deterministic text embedding size for retrieval chunk indexing |
| `VECTOR_PROVIDER` | `milvus` | Enables Milvus REST vector index with PostgreSQL fallback |
| `MILVUS_HOST` | `milvus` | Internal Milvus REST host |
| `MILVUS_PORT` | `19530` | Internal Milvus REST port |
| `MILVUS_COLLECTION` | `meeting_chunks` | Milvus collection for derived meeting chunk vectors |
| `LLM_TIMEOUT_SECONDS` | `60` | LLM provider HTTP timeout |
| `LLM_MAX_RETRIES` | `1` | Retry count for retryable LLM provider failures |
| `LLM_RETRY_BACKOFF_SECONDS` | `0.2` | Linear retry backoff base for LLM provider calls |
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
| `http://127.0.0.1:15672/` | `200` |
| `http://127.0.0.1:9001/` | `200` |
| `http://127.0.0.1:9096/-/healthy` | `200` |
| `http://127.0.0.1:5540/` | `200` |

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
| Uploaded `.wav` meeting processed through RabbitMQ/Celery | Meeting `READY`, job `SUCCEEDED` |
| `GET /api/meetings/{meetingId}/intelligence-result` | Returned `meeting-intelligence-result.v1` |
| `GET /api/meetings/{meetingId}/transcript` and `/insights` | Returned persisted processed JSON sections |
| LLM provider selection and fallback tests | Passed |
| LLM analysis merge and deterministic fallback tests | Passed |
| Worker idempotency, lock, and provider-failure state tests | Passed |
| Text transcript extraction and text-upload processing tests | Passed |
| Derived transcript/insight index persistence tests | Passed |
| Provider retry and worker `RETRYING` tests | Passed |
| Backend `unittest` suite after completed processing pipeline | 21 tests passed |

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

*Document reflects project state at **Phase 5 - Retrieval And Chat** complete. Frontend, backend, worker, gateway, PostgreSQL, Redis, RabbitMQ, MinIO, Milvus, Prometheus, text transcript extraction, LLM provider configuration, configurable LLM analysis, derived transcript/insight/chunk indexes, local text embedding fallback, Milvus REST vector upsert/search, evidence-guarded meeting chat history, chat citations, frontend chat tab, and worker safety tests are wired in Compose.*
