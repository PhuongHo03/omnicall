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
