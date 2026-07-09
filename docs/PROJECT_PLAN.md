# Omnicall Planning Index

Canonical planning now lives under `docs/plans/`.

- `docs/plans/0 - project overview.md` - project-wide context, structure, runtime info, and phase summary.
- `docs/plans/1 - repository foundation.md` - completed foundation phase.
- `docs/plans/2 - local runtime and infrastructure.md` - Docker Compose, gateway, and internal services.
- `docs/plans/3 - meeting upload and core records.md` - meeting creation, upload, MinIO, PostgreSQL, and job enqueueing.
- `docs/plans/4 - processing pipeline.md` - async transcription and insight extraction.
- `docs/plans/5 - retrieval and chat.md` - vector retrieval and meeting-grounded chat.
- `docs/plans/5.5 - voice processing and rerank.md` - completed local voice ASR command path, speaker labeling, and local/Ollama rerank.
- `docs/plans/5.6 - local guardrails.md` - completed local/Ollama guardrail workflow around transcript, RAG, and chat output.
- `docs/plans/6 - admin and operations.md` - completed Prometheus, backend admin metrics endpoint, Redis metrics cache, and frontend admin dashboard.
- `docs/plans/7 - hardening.md` - completed account auth, Admin/User roles, account file storage, safe meeting-session deletion, security, privacy, reliability, and final verification.
- `docs/plans/8 - operational logs.md` - completed temporary Redis operational logs for processing and RAG.
- `docs/plans/9 - full json rag coverage.md` - completed full processed-JSON retrieval coverage for smarter meeting chat.

Project documentation rules:

- `docs/rules/update-planning.md`
- `docs/rules/update-explanation.md`

- `docs/plans/10 - frontend backend resilience.md` - frontend request protection, backend rate limiting, concurrency guards, and circuit breakers.

- `docs/plans/11 - resilience hardening.md` - Redis pool, fallback rate-limit, circuit breaker wiring, frontend abort/retry, rate-limit refinements.
- `docs/plans/12 - voice processing upgrade.md` - ASR whisper-medium upgrade, configurable model settings, diarization overlap ratio matching, dynamic confidence.
- `docs/plans/13 - guardrail scope reduction.md` - remove transcript and retrieved-context guardrail layers, keep input/output guardrails only, and update related docs/env/runtime references.
- `docs/plans/14 - guardrail intelligence upgrade.md` - parser hardening, category normalization, per-layer strict mode, output soft block/redaction, confidence heuristics, latency budget, observability metadata, orchestration tests.
- `docs/plans/15 - guardrail simplification and threshold control.md` - simplify actions to allowed/blocked, remove redaction strategy, regex pre-check, few-shot Vietnamese prompt, post-verdict category validation, input→output trust boost, text length guard, stale env cleanup.

- `docs/plans/17 - typewriter-expansion.md` - expand typewriter effect to all evidence states (grounded, partial, not_enough_evidence, fast_path, blocked, error).
