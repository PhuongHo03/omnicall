# Worker Explanation

## Structure

The worker reuses the backend package and runs as a separate Compose service.

```text
backend/
├── configs/
│   └── celery_app.py                  <- Celery app, broker URL, queue routing
├── providers/
│   ├── analysis_provider.py           <- LLM-backed processed JSON provider and result normalization
│   ├── embedding_provider.py          <- Ollama text embedding provider
│   ├── guardrail_provider.py          <- Ollama guardrail provider boundary
│   ├── llm_provider.py                <- API/endpoint/Ollama LLM adapters and fallback
│   ├── lock_provider.py               <- Redis lock provider
│   ├── operational_log_provider.py    <- Temporary Redis Stream event adapter
│   ├── text_extraction_provider.py    <- Text transcript and notes extraction
│   ├── transcript_types.py            <- Shared transcript segment value type
│   ├── transcription_provider.py      <- Text/voice transcription routing provider
│   ├── voice_provider.py              <- ffmpeg audio preprocessing, local VAD, ASR and diarization provider boundary
│   ├── rerank_provider.py             <- Local model rerank command boundary
│   └── vector_provider.py             <- Milvus REST vector index adapter
├── model_runners/
│   ├── asr.py                         <- faster-whisper CLI runner for local ASR
│   ├── diarization.py                 <- WeSpeaker CLI runner for local diarization
│   └── rerank.py                      <- SentenceTransformers cross-encoder CLI runner
├── repositories/
│   ├── meeting_repository.py          <- Meeting, asset, job, result persistence
│   └── retrieval_repository.py        <- Retrieval chunk persistence
├── services/
│   ├── processing_pipeline_service.py <- Worker use case and state transitions
│   ├── processing_reconciliation_service.py <- Stale pending-job recovery use case
│   └── retrieval_index_service.py     <- Processed JSON retrieval chunk builder
└── tasks/
    ├── maintenance_tasks.py            <- Periodic reconciliation task boundary
    └── processing_tasks.py             <- Thin meeting-processing task boundary
```

## Runtime Flow

The backend queues work after a meeting asset is uploaded:

```text
POST /api/meetings/{meetingId}/process
-> processing_jobs row
-> meeting status QUEUED
-> Celery task sent to RabbitMQ queue meeting-processing
-> worker consumes task
-> Redis lock lock:meeting-processing:{meetingId}
-> PostgreSQL state reload
-> text extraction or ffmpeg voice preprocessing
-> local VAD speech-region detection for voice assets
-> ASR and diarization provider boundary
-> analysis provider
-> meeting_intelligence_results JSONB upsert
-> meeting_chunks rebuild with local text embeddings
-> Milvus vector upsert when VECTOR_PROVIDER=milvus
-> job SUCCEEDED and meeting READY
-> structured processing events remain temporarily available to Admin logs
```

The Celery task is intentionally thin. It opens a database session, constructs providers, and delegates to `ProcessingPipelineService.process_meeting`. Business state checks and mutations live in the service layer, not in the task decorator.

`ProcessingPipelineService` also emits bounded structured events through `OperationalLogService`. Events cover worker delivery, lock decisions, voice/text transcription, VAD, ASR, diarization, guardrails, primary/fallback LLM analysis, persistence, embedding, Milvus upsert, and final result/failure. Redis logging is fail-open and does not alter job state if the stream is unavailable.

Celery Beat sends `omnicall.processing.reconcile_pending_jobs` to the durable `processing-maintenance` queue every 60 seconds. `ProcessingReconciliationService` takes a global Redis lock, finds jobs that remain `PENDING` while their meeting remains `QUEUED` for more than 120 seconds, and republishes the original task with the same job and meeting IDs. Successful republish updates reconciliation metadata and `updated_at`, creating a cooldown before the next stale check. Broker failures leave the job unchanged for a later cycle.

## Idempotency And State

Worker idempotency currently uses three layers:

| Layer | Behavior |
|---|---|
| PostgreSQL job status | Already `SUCCEEDED` jobs are skipped |
| Redis lock | Prevents concurrent processing for the same meeting |
| Result uniqueness | `meeting_id + schema_version` is unique for `meeting_intelligence_results` |
| Durable task delivery | Processing and maintenance queues are durable; task messages are persistent |
| Late acknowledgment | Interrupted processing is rejected back to RabbitMQ if the worker process is lost |
| Periodic reconciliation | Orphaned `PENDING`/`QUEUED` jobs are republished after the stale threshold |

If a meeting or uploaded asset is missing, the job is marked `FAILED` and the meeting is marked `FAILED` when possible. If processing raises an exception, the worker stores a user-safe failure reason and keeps the internal error in the database only.

Already `SUCCEEDED` jobs return `skipped` without calling transcription or analysis providers again. Locked meetings return `locked` without mutating the pending job or meeting state. Failed jobs being processed again transition through `RETRYING` before `RUNNING`. Current explicit statuses used by the worker are `RUNNING`, `RETRYING`, `SUCCEEDED`, and `FAILED`.

If a database flush fails during processing, the pipeline rolls back the failed transaction and reloads the job and meeting before attempting to persist a safe failure state. If those records were deleted concurrently, the task returns `missing` instead of writing through a poisoned SQLAlchemy session.

Phase 7 did not move processing work into the HTTP request path. Admin meeting-session deletion remains a backend service use case, but it deliberately cleans the worker-derived artifacts for a meeting: processed JSON, retrieval chunks, chat history, meeting assets, MinIO objects, and derived Milvus vectors. The worker still owns asynchronous processing; the admin delete use case owns explicit cleanup.

Admin meeting and account deletion use the same Redis lock namespace as the worker: `lock:meeting-processing:{meetingId}`. If a worker already holds the lock, deletion returns a safe conflict instead of racing the worker. If deletion acquires the lock first, queued processing tasks are revoked best-effort by Celery task ID before the database and object-storage cleanup runs. Worker tasks use `job_id` as the Celery `task_id`, so queued work can be targeted for revoke. If an old or already-delivered task still runs after deletion, it reloads PostgreSQL state and returns `missing` without recreating deleted records.

## Processed Result

Successful processing writes a complete JSON document with schema:

```text
meeting-intelligence-result.v1
```

The current local providers create:

| Section | Current behavior |
|---|---|
| `transcript.segments` | Text uploads parse transcript lines directly; voice uploads use preprocessing/VAD/default local ASR and diarization command runners; missing or failed ASR now fails the job safely instead of producing placeholder text |
| `summary` | Executive summary, detailed summary, and key points |
| `analysis` | All planned section keys are present; missing-evidence sections are empty with reasons |
| `citations` | Citations linked to source transcript segments or generated fallback segments |
| `quality` | Warnings for text extraction, local ASR, diarization, provider failures, or transcript guardrails |

This proves the contract needed by RAG work. Analysis generation uses the configured LLM boundary, so a real endpoint/API or Ollama fallback model must be available for successful processing.

For `.txt`, `.md`, `.vtt`, and `.srt` uploads, the worker uses `DocumentTextExtractionProvider` to read the uploaded object from MinIO and parse lines into transcript segments. Timestamp/speaker lines such as `00:30 Bob: Follow up next week` preserve timing and speaker labels. In this path, the persisted result records `source.transcriptionProvider=local-text-extraction`.

For audio/video uploads, the worker keeps the original asset bytes in MinIO, writes a stable per-asset derived temporary audio file under `/tmp/omnicall-audio`, and normalizes supported media to 16 kHz mono WAV through `ffmpeg`. The raw temporary input is deleted after preprocessing; only derived audio is left locally for downstream model steps. Repeated worker retries reuse a valid derived WAV instead of creating duplicate normalized files. `LocalVADProvider` then detects speech windows with a configurable local energy threshold before the ASR adapter is called. `LocalASRProvider` calls the repository-owned `backend.model_runners.asr` runner and uses `faster-whisper` CPU `int8`. ASR and diarization subprocess timeouts use `max(ASR_TIMEOUT_SECONDS, audioDurationSeconds * ASR_TIMEOUT_REALTIME_FACTOR)`, so longer voice files are not killed at the minimum timeout. `LocalCommandDiarizationProvider` calls the repository-owned `backend.model_runners.diarization` runner and uses WeSpeaker speaker embedding/diarization. Compose mounts the shared `model_cache` volume at `/models`, and `model-init` downloads the fixed ASR, diarization, and rerank model snapshots there before the worker starts. Processing logs resolve the transcription route before the start event, so audio/video sessions show the ASR provider/model instead of the transcription router placeholder.

Voice pipeline failures are safe failures. Preprocessing, ASR, or diarization errors are captured as provider metadata and safe job failure reasons instead of exposing internal stack traces to users. VAD errors can continue without speech-region hints and are recorded as warnings.

After transcription and before analysis generation, the worker runs the transcript guardrail when `GUARDRAIL_TRANSCRIPT_ENABLED=true`. Guardrail metadata is persisted under `source.guardrails.transcript` and job `providerMetadata.guardrails.transcript`. Non-strict mode downgrades blocked transcript decisions to warnings so normal business meetings are not overblocked; strict mode fails closed with a safe failure state when the provider errors or returns a block decision.

## LLM Provider Boundary

`backend/providers/llm_provider.py` provides the shared LLM boundary for future analysis and chat work:

| Provider | Purpose |
|---|---|
| `OpenAICompatibleLLMProvider` | Calls `/chat/completions` on external APIs or private OpenAI-compatible endpoints |
| `CustomJSONEndpointLLMProvider` | Calls a custom `/generate-json` endpoint and accepts `json`, `content`, or `result` fields |
| `OllamaLLMProvider` | Calls local Ollama `/api/chat` with `format: json` |
| `FallbackLLMProvider` | Tries the primary provider and falls back to Ollama on provider errors |

The worker receives LLM credentials through environment variables only. The primary LLM can be an API/private endpoint, and `FallbackLLMProvider` can fall back to the Compose Ollama service.

The worker uses `LLMAnalysisProvider` to ask the configured LLM for JSON intelligence sections, preserves the authoritative transcript generated by the transcription provider, validates the final result before marking the meeting `READY`, and fails the job safely if no LLM path can produce valid JSON. Analysis prompts keep segment IDs, speakers, and text as compact `segmentId|speaker|text` lines while omitting timestamps/confidence already preserved in the canonical transcript. When `LLM_PROVIDER=endpoint` or `api` and `LLM_FALLBACK_PROVIDER=ollama`, the API/private endpoint is tried first; local fallback uses its own timeout and context-window settings, and persisted provider metadata records the effective provider/model that actually generated the JSON.

## Retrieval Indexing

After a processed result is stored, the worker rebuilds `meeting_chunks` from the same JSON. The chunk builder covers the processed JSON broadly: meeting metadata, source/provider/model/voice/guardrail metadata, participants, summary, analysis sections, empty-section explanations, transcript coverage, quality warnings, citation overview, and transcript fallback segments. Structured and metadata sections get higher retrieval priority than transcript fallback chunks. Transcript fallback chunks preserve speaker, confidence, source segment IDs, and time ranges so later chat answers can cite source evidence.

The embedding path uses `OllamaEmbeddingProvider` with the configured local `EMBEDDING_MODEL`. `ollama-init` pulls `EMBEDDING_MODEL`, `OLLAMA_MODEL`, and `GUARDRAIL_MODEL` into `ollama_data` before backend and worker start. Test-only embedding fixtures live under `backend/tests/`; production indexing no longer uses hash embeddings.

When `VECTOR_PROVIDER=milvus`, the worker upserts derived chunk vectors through the Milvus REST API after PostgreSQL `meeting_chunks` are flushed. The vector payload includes stable references such as meeting ID, result ID, chunk ID, JSON pointer, source type, section type, and time range. Milvus remains derived infrastructure: if vector upsert fails, the meeting can still succeed and the job payload records `retrievalMetadata.vectorIndex.status=failed`.

If the configured embedding dimension changes, the Milvus provider checks the existing collection schema and recreates the derived `meeting_chunks` collection when its vector dimension no longer matches `EMBEDDING_DIMENSIONS`. PostgreSQL chunk rows remain authoritative, so collection recreation does not delete product truth.

## Compose Behavior

The Compose worker command is:

```bash
celery -A backend.configs.celery_app.celery_app worker --loglevel=INFO --queues=meeting-processing,processing-maintenance --concurrency=1 --hostname=worker@%h --without-gossip --without-mingle
```

The separate `beat` service publishes periodic maintenance tasks. Celery remote control is enabled in `backend/configs/celery_app.py` so admin deletion can revoke queued meeting-processing tasks by job ID. RabbitMQ 4 permits Celery's transient non-exclusive pidbox queues through its source-controlled compatibility setting. The worker command still disables gossip and mingle, while the worker healthcheck targets its node with `celery inspect ping` so broker socket availability alone cannot hide a stopped consumer.

## Verification

Phase 4 worker slice verification used:

```bash
python3 -m compileall backend
docker compose config
docker compose exec -T backend alembic current
docker compose ps backend worker beat nginx
docker compose exec -T backend python -m unittest discover -s backend/tests -v
```

The current verification split is intentional: API tests prove safe enqueue/failure behavior without real local model binaries, and service tests prove successful processing using test-only model fixtures.

| Check | Result |
|---|---|
| API upload/process without configured ASR/LLM models | Job fails safely and remains retryable |
| Pipeline service with test-only model fixtures | Meeting reaches `READY` and persists result/index rows |
| Result schema | `meeting-intelligence-result.v1` |
| LLM provider selection and fallback tests | Passed |
| LLM analysis merge and provider failure tests | Passed |
| Worker idempotency, lock, and provider-failure state tests | Passed |
| Text transcript extraction and text-upload processing tests | Passed |
| Processed JSON and derived `meeting_chunks` persistence tests | Passed |
| Provider retry and `RETRYING` transition tests | Passed |
| Retrieval chunk builder and test-only embedding fixture tests | Passed |
| Milvus vector upsert smoke check | `status=upserted` |
| Milvus vector search with PostgreSQL chunk reload smoke check | Passed |
| Voice provider contract, WAV metadata fallback, idempotent audio preprocessing, local energy VAD, ASR failure, local command ASR, local-only ASR selection, and diarization command tests | Passed |
| Voice warning persistence to processed JSON and job metadata | Passed |
| Rerank integration test | Passed |
| Rerank command and unavailable-command tests | Passed |
| Guardrail provider normalization, prompt-injection, output downgrade, strict/non-strict failure, and transcript warning persistence tests | Passed |
| Backend unittest suite after model-provider standardization | 54 tests passed |

Phase 5.5 and 5.6 end-to-end verification on 2026-06-17 also confirmed:

| Check | Result |
|---|---|
| `backend.model_runners.asr` over MP3 | Produced real transcript segments |
| `backend.model_runners.diarization` over normalized WAV | Produced speaker assignments |
| `backend.model_runners.rerank` | Returned ranked chunk IDs |
| Voice MP3 upload and processing through gateway | Meeting reached `READY` and latest job reached `SUCCEEDED` |
| Voice-derived processed JSON | Included ASR, diarization, ffmpeg, source voice metadata, transcript segments, and guardrail warning metadata |
| Retrieval index rebuild | Upserted 3 chunks into Milvus after collection dimension recovery |
| Chat over the voice-derived meeting | Returned a grounded cited answer with rerank and input/context/output guardrail metadata |

Phase 7 hardening verification on 2026-06-17 also confirmed:

| Check | Result |
|---|---|
| Full backend unittest suite, including worker/retrieval/provider/reconciliation tests | 82 tests passed |
| Targeted auth/file/admin deletion tests | Passed |
| Admin meeting deletion cleanup for worker-derived records | Passed in targeted service test and gateway smoke |
| Admin deletion processing-lock and queued-task revoke behavior | Passed |

Phase 8 operational-log verification on 2026-06-19 also confirmed:

| Check | Result |
|---|---|
| Full backend unittest suite with processing/RAG event tests | 87 tests passed |
| Worker event stages | Receive/lock, transcription, voice models, analysis, persistence, embedding, vector upsert, result/failure |
| Runtime worker health after image recreation | Healthy |

*Document reflects project state after Phase 9 full JSON RAG coverage updates on **2026-06-25**. Worker model runners and specialized model paths are repository-owned contracts; `.env` retains only operator-facing timeouts, thresholds, retrieval limits, and Ollama choices. Existing delivery, retry, reconciliation, logging, persistence, retrieval, and cleanup behavior remains verified.*
