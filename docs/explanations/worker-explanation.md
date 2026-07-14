# Worker Explanation

## Structure

The worker reuses the backend package and runs as a separate Compose service.

```text
backend/
├── configs/
│   └── celery_app.py                  <- Celery app, broker URL, queue routing
├── providers/
│   ├── analysis/
│   │   └── provider.py                <- LLM-backed processed JSON provider and result normalization
│   ├── embedding_provider.py          <- Ollama text embedding provider
│   ├── guardrail_provider.py          <- Ollama guardrail provider boundary
│   ├── llm/
│   │   ├── provider.py                <- API/endpoint/Ollama LLM adapters and fallback
│   │   └── transport.py               <- Shared HTTP transport and response parsing
│   ├── lock_provider.py               <- Redis lock provider
│   ├── operational_log_provider.py    <- Temporary Redis Stream event adapter
│   ├── transcript_types.py            <- Shared transcript segment value type
│   ├── transcription_provider.py      <- Text/voice transcription routing provider
│   ├── voice/
│   │   └── provider.py                <- ffmpeg audio preprocessing, local VAD, ASR and diarization provider boundary
│   ├── rerank_provider.py             <- Local model rerank command boundary
│   └── vector_provider.py             <- Milvus REST vector index adapter
├── model_runners/
│   ├── asr.py                         <- faster-whisper CLI runner for local ASR
│   ├── diarization.py                 <- WeSpeaker CLI runner for local diarization
│   └── rerank.py                      <- SentenceTransformers cross-encoder CLI runner
├── repositories/
│   ├── meeting_repository.py          <- Meeting, asset, and result persistence
│   └── retrieval_repository.py        <- Retrieval chunk persistence
├── services/
│   ├── processing_pipeline_service.py <- Worker use case and state transitions
│   ├── processing_reconciliation_service.py <- Stale pending-job recovery use case
│   └── retrieval/                     <- Chunking, indexing, candidate, and search boundaries
└── tasks/
    ├── maintenance_tasks.py            <- Periodic reconciliation task boundary
    └── processing_tasks.py             <- Thin meeting-processing task boundary
```

## Runtime Flow

The backend queues work after a meeting asset is uploaded:

```text
POST /api/meetings/{meetingId}/process
-> meeting status QUEUED
-> Celery task sent to RabbitMQ queue meeting-processing
-> worker consumes task
-> Redis lock lock:meeting-processing:{meetingId}
-> PostgreSQL state reload
-> ffmpeg voice preprocessing
-> local VAD speech-region detection for voice assets
-> ASR and diarization provider boundary
-> analysis provider
-> meeting_intelligence_results JSONB upsert
-> meeting_chunks rebuild with local text embeddings
-> Milvus vector upsert when VECTOR_PROVIDER=milvus
-> meeting READY
-> structured processing events remain temporarily available to Admin logs
```

The Celery task is intentionally thin. It opens a database session, constructs providers, and delegates to `ProcessingPipelineService.process_meeting`. Business state checks and mutations live in the service layer, not in the task decorator.

`ProcessingPipelineService` also emits bounded structured events through `OperationalLogService`. Events cover worker delivery, lock decisions, voice transcription, VAD, ASR, diarization, guardrails, primary/fallback LLM analysis, persistence, embedding, Milvus upsert, and final result/failure. Redis logging is fail-open and does not alter job state if the stream is unavailable.

Celery Beat sends `omnicall.processing.reconcile_pending_meetings` to the durable `processing-maintenance` queue on the configured interval. `ProcessingReconciliationService` takes a global Redis lock, finds meetings that remain `QUEUED` beyond the stale threshold, republishes processing by meeting ID, and also clears stale `pending_chat_status="started"` values. Chat task failures independently reset the pending status, persist one safe error response per user message, and publish an error event. Broker failures leave the meeting eligible for a later cycle.

## Idempotency And State

Worker idempotency currently uses three layers:

| Layer | Behavior |
|---|---|
| PostgreSQL meeting status | Already `READY` meetings are skipped |
| Redis lock | Prevents concurrent processing for the same meeting |
| Result uniqueness | `meeting_id + schema_version` is unique for `meeting_intelligence_results` |
| Durable task delivery | Processing and maintenance queues are durable; task messages are persistent |
| Late acknowledgment | Interrupted processing is rejected back to RabbitMQ if the worker process is lost |
| Periodic reconciliation | Stale `QUEUED` meetings are republished after the stale threshold |

If a meeting or uploaded asset is missing, the meeting is marked `FAILED` when possible. If processing raises an exception, the worker stores a user-safe failure reason and logs the internal error through operational logs.

Already `READY` meetings return `skipped` without calling transcription or analysis providers again. Locked meetings return `locked` without mutating meeting state. Failed meetings can be queued again and move through `QUEUED` and `PROCESSING` before becoming `READY` or `FAILED`.

If a database flush fails during processing, the pipeline rolls back the failed transaction and reloads the meeting before attempting to persist a safe failure state. If the meeting was deleted concurrently, the task returns `missing` instead of writing through a poisoned SQLAlchemy session.

Phase 7 did not move processing work into the HTTP request path. Admin meeting-session deletion remains a backend service use case, but it deliberately cleans the worker-derived artifacts for a meeting: processed JSON, retrieval chunks, chat history, meeting assets, MinIO objects, and derived Milvus vectors. Vector cleanup is required before the PostgreSQL rows are deleted; if Milvus is unavailable, deletion returns a retryable `503` and preserves the meeting data. The worker still owns asynchronous processing; the admin delete use case owns explicit cleanup.

Admin meeting and account deletion use the same Redis lock namespace as the worker: `lock:meeting-processing:{meetingId}`. If a worker already holds the lock, deletion returns a safe conflict instead of racing the worker. If deletion acquires the lock first, queued processing tasks must be revoked successfully by meeting ID before the database and object-storage cleanup runs; queue revoke failure returns a retryable `503` and preserves the meeting. If an old or already-delivered task still runs after deletion, it reloads PostgreSQL state and returns `missing` without recreating deleted records.

## Processed Result

Successful processing writes a complete JSON document with schema:

```text
meeting-intelligence-result.v2
```

The current local providers create:

| Section | Current behavior |
|---|---|
| `transcript.segments` | Text uploads parse transcript lines directly; voice uploads use preprocessing/VAD/default local ASR and diarization command runners; missing or failed ASR now fails the job safely instead of producing placeholder text |
| `evidence.items` | Canonical transcript, structured, derived, and source evidence records; transcript items retain deterministic quotes and time ranges |
| `speakers` | Deterministic speaker count, talk time, segment count, and participant mapping metadata derived from transcript speaker labels |
| `participants`, `entities`, `facts`, `events`, `relationships` | RAG-first knowledge records generated by LLM candidate extraction and normalized/validated against canonical IDs and citations |
| `topics`, `summaries` | Hierarchical topic records and executive/topic/timeline summaries with citation and topic references |
| `actions`, `decisions`, `risks`, `questions` | Canonical task/decision/risk/question records with owners/statuses/confidence/citations when available |
| `quality`, `extraction` | Transcript/source quality, extraction confidence, unsupported claims, and warnings |

This proves the contract needed by RAG work. Analysis generation uses the configured LLM boundary, so a real endpoint/API or Ollama fallback model must be available for successful processing.

Meeting processing is voice-only. Text transcript or notes files are rejected by the meeting upload allowlist before they can enter the worker. For audio/video uploads, the worker keeps the original asset bytes in MinIO, writes a stable per-asset derived temporary audio file under `/tmp/omnicall-audio`, and normalizes supported media to 16 kHz mono WAV through `ffmpeg`. The raw temporary input is deleted after preprocessing; only derived audio is left locally for downstream model steps. Repeated worker retries reuse a valid derived WAV instead of creating duplicate normalized files. `LocalVADProvider` then detects speech windows with a configurable local energy threshold before the ASR adapter is called. `LocalASRProvider` calls the repository-owned `backend.model_runners.asr` runner and uses `faster-whisper` with configurable model, compute type, beam size, and language via `ASR_MODEL` (default `whisper-medium`), `ASR_COMPUTE_TYPE`, `ASR_BEAM_SIZE`, and `ASR_LANGUAGE` environment variables. ASR and diarization subprocess timeouts use `max(ASR_TIMEOUT_SECONDS, audioDurationSeconds * ASR_TIMEOUT_REALTIME_FACTOR)`, so longer voice files are not killed at the minimum timeout. `LocalCommandDiarizationProvider` calls the repository-owned `backend.model_runners.diarization` runner and uses WeSpeaker speaker embedding/diarization. Speaker assignment uses overlap ratio scoring: each ASR segment is matched to the diarization turn with the highest weighted score (`0.7 * overlap_ratio + 0.3 * turn_confidence`). Segments with overlap ratio below a minimum threshold (5% for segments under 500ms, 10% for longer segments) keep their original speaker label instead of forcing assignment. Confidence is calculated dynamically as `turn_confidence * overlap_ratio` instead of using a hardcoded value. Compose mounts the shared `model_cache` volume at `/models`, and `model-init` downloads the fixed ASR (`Systran/faster-whisper-medium`), diarization, and rerank model snapshots there before the worker starts.

Voice pipeline failures are safe failures. Preprocessing, ASR, or diarization errors are captured as provider metadata and safe job failure reasons instead of exposing internal stack traces to users. VAD errors can continue without speech-region hints and are recorded as warnings.

After transcription, the active processing path no longer runs a transcript guardrail stage. Older processed results may still contain transcript guardrail metadata, but current worker behavior uses only the remaining active guardrail scope defined by the later chat/output checks.

## LLM Provider Boundary

`backend/providers/llm/provider.py` provides the shared LLM boundary for analysis and chat work. The former flat provider entrypoint is no longer part of the repository; internal imports use the canonical provider package.

| Provider | Purpose |
|---|---|
| `OpenAICompatibleLLMProvider` | Calls `/chat/completions` on external APIs or private OpenAI-compatible endpoints |
| `CustomJSONEndpointLLMProvider` | Calls a custom `/generate-json` endpoint and accepts `json`, `content`, or `result` fields |
| `OllamaLLMProvider` | Calls local Ollama `/api/chat` with `format: json` |
| `FallbackLLMProvider` | Tries the primary provider and falls back to Ollama on provider errors |

The worker receives LLM credentials, Agentic RAG budgets, resilience limits, and circuit-breaker settings through environment variables only. The primary LLM can be an API/private endpoint, and `FallbackLLMProvider` can fall back to the Compose Ollama service. These settings are passed explicitly by Compose so worker-side processing and chat tasks use the same runtime policy as the backend.

The worker uses `LLMAnalysisProvider` to ask the configured LLM for RAG-first candidate knowledge records, preserves deterministic transcript/source/evidence/speaker fields, validates the final result before marking the meeting `READY`, and fails the job safely if no LLM path can produce valid JSON. Analysis prompts now keep segment IDs, speakers, timestamps, confidence, and text as compact `segmentId|speaker|startMs|endMs|confidence|text` lines. The provider normalizes citation IDs, links speakers to participants when speaker labels match, derives a participant-count fact from `speakers`, quarantines malformed or unknown relationship endpoints with quality warnings, creates a transcript-grounded executive-summary fallback when the model returns no summary, and records unsupported claims when important LLM records lack citations or deterministic sources. When `LLM_PROVIDER=endpoint` or `api` and `LLM_FALLBACK_PROVIDER=ollama`, the API/private endpoint is tried first; local fallback uses its own timeout and context-window settings, and persisted provider metadata records the effective provider/model that actually generated the JSON.

## Retrieval Indexing

After a processed result is stored, the worker rebuilds `meeting_chunks` from the same JSON. `backend/services/retrieval/chunk_builder.py` owns pure chunk construction, while `backend/services/retrieval/index_service.py` owns persistence and vector upsert orchestration. Chunk texts are embedded in bounded Ollama batches with retry/backoff and an embedding identity/version recorded in chunk metadata. The chunk builder now covers RAG-first records: meeting/source metadata, speaker stats, participant count facts, generic facts, participant profiles, entities, event timeline records, relationship edges, topics, executive/topic/timeline summaries, actions, decisions, risks, questions, quality/extraction metadata, evidence maps, and transcript windows. Fact/entity/event/relationship/action/decision/risk chunks outrank transcript windows for precise questions; topic and summary chunks support broad questions.

The embedding path uses `OllamaEmbeddingProvider` with the configured local `EMBEDDING_MODEL`. `ollama-init` pulls `EMBEDDING_MODEL`, `OLLAMA_MODEL`, and `GUARDRAIL_MODEL` into `ollama_data` before backend and worker start. Test-only embedding fixtures live under `backend/tests/`; production indexing no longer uses hash embeddings.

When `VECTOR_PROVIDER=milvus`, the worker upserts derived chunk vectors through the Milvus REST API after PostgreSQL `meeting_chunks` are flushed. The vector payload includes stable references such as meeting ID, result ID, chunk ID, index generation, JSON pointer, source type, section type, and time range. Milvus remains derived infrastructure: if vector upsert fails, the meeting can still succeed, the job payload records `retrievalMetadata.vectorIndex.status=failed`, and a bounded `omnicall.processing.repair_retrieval_index` task retries the derived index.

`backend.scripts.rebuild_retrieval_index` now expects Phase 22 RAG-first JSON. Obsolete local processed results must be reprocessed or reset before rebuild; the script fails fast instead of silently indexing old `summary`/`analysis`/`citations` documents.

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
| Result schema | `meeting-intelligence-result.v2` |
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
| Chat over the voice-derived meeting | Returned a grounded cited answer with rerank and input/output guardrail metadata |

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

### Phase 25 Windowed Extraction

After transcription, the processing service builds token-bounded windows without duplicating transcript text. Windows preserve speaker turns where possible, retain timestamps and segment IDs, and use a small overlap for cross-window context. Local LLM results are stored on `meeting_transcript_windows`; reduction merges candidate records, preserves citations/source windows, and writes canonical `knowledge.records` and `knowledge.relationships` into the result JSON. Window extraction has a retryable Celery task and the normal processing path performs bounded parallel extraction before global reduction.

Worker persistence records the `schemaVersion` from the actual result JSON, so hierarchical v2 output is not mislabeled by a static provider constant. `backend/scripts/reprocess_all_meetings_v2.py` clears local derived intelligence artifacts only for meetings with a `MeetingAsset`, deletes meeting-scoped vectors, resets those meetings to `QUEUED`, and enqueues a clean v2 processing run; `--dry-run` reports the scope without mutation. Assetless draft meetings are excluded and remain uploadable.

*Document reflects project state during **Phase 37 Database Reset and V2 Cutover**. Worker processing uses full transcript evidence plus persisted bounded windows, retryable local extraction, v2 reduction, and generation-aware retrieval indexing.*
