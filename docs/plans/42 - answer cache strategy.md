# Phase 42 - Answer cache strategy

## Status: Done

## Objectives

1. Cache grounded independent meeting questions in Redis without weakening guardrails or evidence rules.
2. Invalidate cached results when derived retrieval data changes.

## Tasks

- [x] Add cache TTL, size, enablement, and semantic-threshold settings.
- [x] Add exact and meeting-local semantic Redis lookup with expiration cleanup and fail-open behavior.
- [x] Require the same retrieval index generation and retain input/output guardrails on cache hits.
- [x] Persist cache-hit provenance in chat metadata and invalidate on reindex or meeting deletion.
- [x] Add cache hit/miss metrics and integration tests against Redis.

## Verification Plan

- [x] Python compilation succeeds.
- [x] Verify exact, semantic, stale-generation, and invalidation paths in the Compose runtime. Redis errors remain fail-open by contract and covered by the adapter error handling.

## Completion Report

> **Completed at:** 2026-07-15
> **Verified by:** Container test suite and live Redis exact/semantic/stale/invalidation check.

### What was implemented

- Meeting/index-generation-scoped Redis cache, cache metrics/logging, and invalidation on reindex or meeting deletion.

### What was changed from original plan

- Runtime verification found and fixed an invalidation edge case where a stale-generation lookup had already pruned an entry from the bounded Redis index. Invalidation now scans the meeting key namespace as well.
- Phase 44 supersedes this v1 orchestration with canonical/contextual exact keys, authoritative snapshot and pipeline fingerprints, citation rehydration, embedding/retrieval cache layers, and claim-verified admission. Semantic lookup currently runs in `shadow` with canary `0%`; it does not directly serve until the 99% precision gate is met.

## Related Docs

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md`
