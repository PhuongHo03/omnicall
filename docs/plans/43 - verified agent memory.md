# Phase 43 - Verified agent memory

## Status: Done

## Objectives

1. Turn only user-approved grounded answers into meeting-scoped retrieval strategy hints.
2. Keep raw reasoning and memory-derived facts out of persistence and answer evidence.

## Tasks

- [x] Add additive feedback and agent-memory schema migration.
- [x] Add owner-scoped thumbs up/down API and frontend controls.
- [x] Create/deactivate memory only from eligible feedback and persist structured plan/tool strategy without thoughts.
- [x] Retrieve relevant memory hints before agent planning without bypassing retrieval or citations.
- [x] Run migration and feedback/memory integration tests in the Compose runtime.

## Verification Plan

- [x] Frontend production build and Python compilation succeed.
- [x] Verify up/down overwrite lifecycle and memory relevance fallback. The owner-scoped route remains guarded by meeting ownership before feedback persistence.

## Completion Report

> **Completed at:** 2026-07-15
> **Verified by:** Alembic head check, container integration test, and live worker feedback task lifecycle.

### What was implemented

- Durable feedback and strategy-memory records, owner-scoped feedback API/UI, and asynchronous memory activation/deactivation worker task.

### Notes for future sessions

- Memory persists only structured query-plan/tool strategy. Raw agent thoughts remain excluded and memory cannot serve as factual evidence.
- Phase 44 persists the three-state feedback lifecycle with a monotonically increasing revision. Clicking the selected thumbs button sends and stores `neutral`, the public history maps it to no selected button while retaining the revision, and related memory/cache state is invalidated. Chat history hydrates the effective `up`/`down`/neutral UI state after refresh.
- Phase 44 also binds active memories to the current generation, embedding identity, retrieval contract, pipeline, context, intent, answer shape, and entity set, and revalidates stale strategies after reindex.

## Related Docs

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
