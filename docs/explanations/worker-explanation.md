# Worker Explanation

## Structure

The worker reuses the backend package and runs as a separate Compose service.

```text
backend/
├── configs/
│   └── celery_app.py                  <- Celery app, broker URL, queue routing
├── providers/
│   ├── analysis_provider.py           <- Deterministic processed JSON provider stub
│   ├── embedding_provider.py          <- Deterministic local text embedding fallback
│   ├── llm_provider.py                <- API/endpoint/Ollama LLM adapters and fallback
│   ├── lock_provider.py               <- Redis lock provider
│   ├── text_extraction_provider.py    <- Text transcript and notes extraction
│   ├── transcript_types.py            <- Shared transcript segment value type
│   ├── transcription_provider.py      <- Deterministic transcript provider stub
│   └── vector_provider.py             <- Milvus REST vector index adapter
├── repositories/
│   ├── meeting_repository.py          <- Meeting, asset, job, result persistence
│   └── retrieval_repository.py        <- Retrieval chunk persistence
├── services/
│   ├── processing_pipeline_service.py <- Worker use case and state transitions
│   └── retrieval_index_service.py     <- Processed JSON retrieval chunk builder
└── tasks/
    └── processing_tasks.py            <- Thin Celery task boundary
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
-> transcription provider
-> analysis provider
-> meeting_intelligence_results JSONB upsert
-> transcript_segments and meeting_insights rebuild
-> meeting_chunks rebuild with local text embeddings
-> Milvus vector upsert when VECTOR_PROVIDER=milvus
-> job SUCCEEDED and meeting READY
```

The Celery task is intentionally thin. It opens a database session, constructs providers, and delegates to `ProcessingPipelineService.process_meeting`. Business state checks and mutations live in the service layer, not in the task decorator.

## Idempotency And State

Worker idempotency currently uses three layers:

| Layer | Behavior |
|---|---|
| PostgreSQL job status | Already `SUCCEEDED` jobs are skipped |
| Redis lock | Prevents concurrent processing for the same meeting |
| Result uniqueness | `meeting_id + schema_version` is unique for `meeting_intelligence_results` |

If a meeting or uploaded asset is missing, the job is marked `FAILED` and the meeting is marked `FAILED` when possible. If processing raises an exception, the worker stores a user-safe failure reason and keeps the internal error in the database only.

Already `SUCCEEDED` jobs return `skipped` without calling transcription or analysis providers again. Locked meetings return `locked` without mutating the pending job or meeting state. Failed jobs being processed again transition through `RETRYING` before `RUNNING`. Current explicit statuses used by the worker are `RUNNING`, `RETRYING`, `SUCCEEDED`, and `FAILED`.

## Processed Result

Successful processing writes a complete JSON document with schema:

```text
meeting-intelligence-result.v1
```

The current deterministic provider stubs create:

| Section | Current behavior |
|---|---|
| `transcript.segments` | One placeholder segment with speaker, timing, text, and confidence |
| `summary` | Executive summary, detailed summary, and key points |
| `analysis` | All planned section keys are present; missing-evidence sections are empty with reasons |
| `citations` | At least one citation linked to the placeholder transcript segment |
| `quality` | Warnings that real ASR, diarization, and LLM providers are not connected |

This proves the contract needed by RAG work. With default `ANALYSIS_PROVIDER=local`, it does not represent production transcription or analysis quality yet.

For `.txt`, `.md`, `.vtt`, and `.srt` uploads, the worker uses `DocumentTextExtractionProvider` to read the uploaded object from MinIO and parse lines into transcript segments. Timestamp/speaker lines such as `00:30 Bob: Follow up next week` preserve timing and speaker labels. In this path, the persisted result records `source.transcriptionProvider=local-text-extraction`.

## LLM Provider Boundary

`backend/providers/llm_provider.py` provides the shared LLM boundary for future analysis and chat work:

| Provider | Purpose |
|---|---|
| `OpenAICompatibleLLMProvider` | Calls `/chat/completions` on external APIs or private OpenAI-compatible endpoints |
| `CustomJSONEndpointLLMProvider` | Calls a custom `/generate-json` endpoint and accepts `json`, `content`, or `result` fields |
| `OllamaLLMProvider` | Calls local Ollama `/api/chat` with `format: json` |
| `FallbackLLMProvider` | Tries the primary provider and falls back to Ollama on provider errors |

The worker receives LLM credentials through environment variables only. The deterministic analysis provider remains the default active processing path for local Compose, while `ANALYSIS_PROVIDER=llm` enables LLM-backed JSON analysis with deterministic fallback.

When `ANALYSIS_PROVIDER=llm`, the worker uses `LLMAnalysisProvider` to ask the configured LLM for JSON intelligence sections, preserves the authoritative transcript generated by the transcription provider, validates the final result before marking the meeting `READY`, and falls back to deterministic analysis if the LLM provider is unavailable or returns invalid JSON.

## Retrieval Indexing

After a processed result is stored, the worker rebuilds `meeting_chunks` from the same JSON. Structured sections are chunked first and get higher retrieval priority than transcript fallback chunks. Transcript fallback chunks preserve source segment IDs and time ranges so later chat answers can cite source evidence.

The current MVP embedding path uses `LocalHashEmbeddingProvider`, a deterministic local hash embedding provider configured by `EMBEDDING_DIMENSIONS`. It is useful for wiring, repeatable tests, and PostgreSQL fallback indexing, but it is not a production semantic embedding model.

When `VECTOR_PROVIDER=milvus`, the worker upserts derived chunk vectors through the Milvus REST API after PostgreSQL `meeting_chunks` are flushed. The vector payload includes stable references such as workspace ID, meeting ID, result ID, chunk ID, JSON pointer, source type, section type, and time range. Milvus remains derived infrastructure: if vector upsert fails, the meeting can still succeed and the job payload records `retrievalMetadata.vectorIndex.status=failed`.

## Compose Behavior

The Compose worker command is:

```bash
celery -A backend.configs.celery_app.celery_app worker --loglevel=INFO --queues=meeting-processing --concurrency=1 --hostname=worker@%h --without-gossip --without-mingle
```

Celery remote control is disabled in `backend/configs/celery_app.py`. The worker healthcheck opens a TCP connection to RabbitMQ instead of calling `celery inspect ping`, which avoids RabbitMQ 4 rejecting remote-control pidbox transient queues in the local runtime.

## Verification

Phase 4 worker slice verification used:

```bash
python3 -m compileall backend
docker compose --env-file .env.example config
docker compose --env-file .env.example exec -T backend alembic current
docker compose --env-file .env.example ps backend worker nginx
docker compose --env-file .env.example exec -T backend python -m unittest discover -s backend/tests -v
```

An end-to-end gateway check created a meeting, uploaded a `.wav` asset, queued processing, waited for `READY`, and confirmed:

| Check | Result |
|---|---|
| Meeting status | `READY` |
| Job status | `SUCCEEDED` |
| Result schema | `meeting-intelligence-result.v1` |
| Transcript endpoint | Returned persisted transcript section |
| Insights endpoint | Returned persisted summary and analysis sections |
| Complete result endpoint | Returned full persisted JSON |
| LLM provider selection and fallback tests | Passed |
| LLM analysis merge and deterministic fallback tests | Passed |
| Worker idempotency, lock, and provider-failure state tests | Passed |
| Text transcript extraction and text-upload processing tests | Passed |
| Derived `transcript_segments` and `meeting_insights` persistence tests | Passed |
| Provider retry and `RETRYING` transition tests | Passed |
| Retrieval chunk builder and deterministic embedding tests | Passed |
| Milvus vector upsert smoke check | `status=upserted` |
| Milvus vector search with PostgreSQL chunk reload smoke check | Passed |
| Backend unittest suite after Phase 5 completion | 30 tests passed |

*Document reflects project state at **Phase 5 - Retrieval And Chat** complete. Worker execution, Redis locking, JSONB persistence, derived transcript/insight/chunk indexes, local text embedding fallback, Milvus REST vector upsert, text transcript extraction, idempotent skip behavior, safe failure states, `RETRYING`, read APIs, LLM provider selection, configurable LLM analysis, retrieval tests, and live backend API health are implemented.*
