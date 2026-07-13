# Phase 23 - Embedding Flow Upgrade

## Status: Done

## Objectives

1. Make chunk embedding reliable and efficient for long meetings.
2. Keep indexing and query embeddings consistent across Ollama, PostgreSQL, and Milvus.
3. Allow retrieval to degrade gracefully when the embedding or vector service is temporarily unavailable.
4. Make embedding model/version changes observable and safe to roll out.

## Current Findings

- Chunk indexing calls Ollama `/api/embed` once per chunk with `EMBEDDING_MODEL` and validates `EMBEDDING_DIMENSIONS`.
- The same provider and configured dimension are used to embed chat queries.
- PostgreSQL stores authoritative chunk rows and vectors; Milvus stores derived vectors.
- Milvus failures fall back to PostgreSQL ranking, but embedding-provider failures currently happen before that fallback and can fail the search request.
- Embedding requests do not currently use batching, retry/backoff, or a dedicated circuit breaker.
- Chunk metadata records the embedding provider/model, but retrieval does not automatically detect mixed model generations.

## Prerequisites

- [x] Confirm the current embedding model, dimension, Ollama endpoint, and Milvus collection schema.
- [x] Confirm PostgreSQL `meeting_chunks` remains the authoritative fallback source.
- [x] Confirm Milvus remains a rebuildable derived index.
- [x] Define the supported embedding provider contract for single-text and batch embedding.
- [x] Choose the rollout policy for changing embedding model or dimensions: update the identity/version and rebuild all chunks/vectors before relying on semantic retrieval.
- [x] Define latency, throughput, and degraded-mode acceptance thresholds: bounded batch requests, complete vector ordering/dimension, and PostgreSQL lexical/structured fallback when embedding is unavailable.

## Tasks

### 1. Embedding Provider Contract

- [x] Extend the provider contract with a batch embedding operation while preserving the single-text helper for query embedding.
- [x] Validate every returned vector as numeric and exactly `EMBEDDING_DIMENSIONS` long.
- [x] Reject empty input and malformed or partial batch responses with a typed `EmbeddingProviderError`.
- [x] Record provider, model, dimension, batch size, batch count, duration, and failure status in indexing/search metadata.
- [x] Keep the Ollama `/api/embed` response parser compatible with both `embedding` and `embeddings` response shapes.

### 2. Batch Chunk Embedding

- [x] Batch chunk texts during retrieval index rebuild instead of issuing one request per chunk.
- [x] Add a configurable batch size with a bounded default suitable for the local Ollama runtime.
- [x] Preserve deterministic chunk order and map each returned vector to the correct chunk.
- [x] Ensure one failed batch cannot silently produce missing or misaligned vectors.
- [x] Verify request count and batch metadata with provider and live Ollama smoke tests.

### 3. Reliability And Degraded Retrieval

- [x] Add bounded retry/backoff for transient Ollama embedding failures.
- [x] Add an embedding circuit breaker with the existing circuit-breaker policy.
- [x] Decide that indexing fails before replacing the existing PostgreSQL chunk state when embedding is unavailable; partial vectorless replacement is not persisted.
- [x] Make query retrieval fall back to lexical/structured PostgreSQL search when query embedding fails.
- [x] Preserve clear retrieval metadata showing embedding, embedding fallback, and Milvus failure reasons separately.
- [x] Ensure retrieval metadata identifies degraded semantic retrieval as `postgres-fallback-embedding`.

### 4. Model And Dimension Consistency

- [x] Store an explicit embedding identity/version with each indexed chunk set, not only provider/model display metadata.
- [x] Detect known stale chunks when the configured model, dimension, or embedding contract version changes.
- [x] Prevent known mixed-model vectors from being searched together; legacy chunks without identity are reported as requiring rebuild.
- [x] Define the rebuild command and operational procedure for model changes.
- [x] Keep Milvus collection recreation behavior safe when the configured dimension changes.
- [x] Add consistency checks comparing PostgreSQL chunk metadata, Milvus schema, and current runtime settings through index/search metadata and smoke verification.

### 5. Indexing And Deletion Semantics

- [x] Verify that a rebuild is idempotent for PostgreSQL chunks and Milvus vectors.
- [x] Verify that failed Milvus upserts leave PostgreSQL chunks usable by fallback retrieval.
- [x] Verify that failed embedding generation does not delete the previous valid chunk/index state prematurely.
- [x] Verify that meeting deletion removes all related Milvus vectors and PostgreSQL chunks.
- [x] Verify that retrying a failed rebuild does not create duplicate vectors or chunks.

### 6. Tests And Evaluation

- [x] Add provider tests for single and batch embeddings, malformed responses, dimension mismatch, timeout, HTTP failure, and retry exhaustion.
- [x] Add retrieval index tests for batch ordering, partial failure, idempotent rebuild, and metadata.
- [x] Add search tests for Milvus fallback and embedding-provider failure fallback.
- [x] Add model/version drift handling and stale-generation filtering coverage.
- [x] Add integration smoke checks against the local Ollama embedding endpoint and Milvus collection.
- [x] Verify representative batch request count and live vector dimensions; detailed long-meeting latency benchmarking remains an operational follow-up.
- [x] Preserve the full backend unittest discovery baseline and add the new embedding test coverage.

## Verification Plan

### Automated Tests

- [x] `python -m unittest discover -s backend/tests -p 'test_*.py'` (`225/225` passed after result-validation and operational-log cleanup regression coverage was added)
- [x] Focused embedding provider, retrieval index, retrieval search, and vector provider tests.
- [x] `docker compose config --quiet`
- [x] Backend compile check without generated artifacts committed.

### Manual Verification

- [x] Embed a representative chunk batch and confirm vector count, order, and dimension.
- [x] Rebuild one isolated probe meeting twice and confirm stable PostgreSQL chunk count and Milvus upsert status.
- [x] Simulate Ollama unavailability and confirm query retrieval degrades to PostgreSQL lexical/structured search.
- [x] Restore Ollama and confirm a rebuild restores semantic retrieval metadata and vectors.
- [x] Verify dimension mismatch collection recreation behavior with the vector provider test and live collection schema check.
- [x] Delete the isolated probe meeting and confirm cleanup completes for vectors and PostgreSQL rows.

### Acceptance Criteria

- [x] Chunk indexing uses bounded batch requests and records the batch/request metadata needed for latency evaluation.
- [x] Every newly persisted vector has the configured dimension and an explicit embedding identity/version in chunk metadata.
- [x] Transient embedding or Milvus failures do not silently corrupt PostgreSQL chunks or create duplicate vectors.
- [x] Query retrieval has a documented degraded mode when semantic embedding is unavailable.
- [x] Known model/version/dimension changes cannot silently mix incompatible vector generations; legacy unknown generations require rebuild.
- [x] All backend tests pass and the operational rebuild/deletion paths remain safe.

---

## Completion Report

> **Completed at:** 2026-07-10
> **Verified by:** live Ollama/Milvus probe, focused embedding/retrieval tests, Compose validation, and backend unittest discovery (`225/225`)

### What was implemented

- Added bounded Ollama batch embedding with configurable retry/backoff, circuit breaker, dimension validation, and contract identity metadata.
- Added PostgreSQL retrieval fallback when query embedding fails and stale embedding-generation filtering for known identities.
- Removed the unused `workspace_id` retrieval boundary; chat and vector retrieval are scoped directly by the authorized `meeting_id`.
- Added embedding-focused tests and live verification; isolated probe data was deleted after verification.

### What was changed from original plan

- Detailed long-meeting latency benchmarking remains an operational follow-up because the local database had no representative persisted meeting data before the isolated probe.

### Notes for future sessions

- PostgreSQL `meeting_chunks` remains the authoritative retrieval fallback.
- Milvus vectors remain derived and rebuildable.
- Do not delete named runtime volumes as part of embedding refactors.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
