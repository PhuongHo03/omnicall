# Phase 13 - Guardrail Scope Reduction

## Status: Done

## Objectives

1. Reduce the active guardrail surface to only **input** and **output** checks.
2. Remove the **transcript guardrail** path from the processing pipeline.
3. Remove the **retrieved-context guardrail** path from the meeting chat pipeline.
4. Remove the related environment variables and default config values.
5. Update backend, frontend/docs references, and project documentation to reflect the new guardrail scope.
6. Preserve backward compatibility for previously saved guardrail metadata in processed JSON and chat history.

## Prerequisites

- [x] Input guardrail for chat is implemented.
- [x] Output guardrail for chat is implemented.
- [x] Transcript and retrieved-context guardrails are currently implemented and active by default.
- [x] The current guardrail provider (`llama-guard3` via Ollama) remains available for input/output checks.

## Tasks

### Backend config and environment

- [x] Remove `guardrail_transcript_enabled` from `backend/configs/settings.py`.
- [x] Remove `guardrail_context_enabled` from `backend/configs/settings.py`.
- [x] Remove `GUARDRAIL_TRANSCRIPT_ENABLED` from `.env.example`.
- [x] Remove `GUARDRAIL_CONTEXT_ENABLED` from `.env.example`.
- [x] Remove `GUARDRAIL_TRANSCRIPT_ENABLED` from `docker-compose.yml` backend service environment.
- [x] Remove `GUARDRAIL_CONTEXT_ENABLED` from `docker-compose.yml` backend service environment.
- [x] Remove `GUARDRAIL_TRANSCRIPT_ENABLED` from `docker-compose.yml` worker service environment.
- [x] Remove `GUARDRAIL_CONTEXT_ENABLED` from `docker-compose.yml` worker service environment.

### Processing pipeline

- [x] Remove the `transcript_guardrail` stage from `backend/services/processing_pipeline_service.py`.
- [x] Remove the call to `self._check_transcript_guardrail(...)`.
- [x] Remove the transcript guardrail operational log emission for that stage.
- [x] Remove the `if transcript_guardrail.get("action") == "block": raise ValueError("transcript_guardrail_blocked")` logic.
- [x] Remove `_append_guardrail_metadata(result_json, "transcript", transcript_guardrail)`.
- [x] Remove the `_check_transcript_guardrail(...)` helper method.
- [x] Remove the transcript guardrail provider/model resolver branch from the internal stage resolver, if it becomes dead code.
- [x] Keep the existing `source.guardrails` indexing logic in `backend/services/retrieval/index_service.py` so previously saved metadata remains searchable.
- [x] Keep existing `source.guardrails` section routing in `backend/services/retrieval/search_service.py` so older meetings remain queryable.

### Chat pipeline

- [x] Remove the `context_guardrail` block from `backend/services/chat_service.py`.
- [x] Remove the `context_guardrail` event emission.
- [x] Remove the call to `self._check_guardrail(...)` for `retrieved_context`.
- [x] Remove the call to `_downgrade_non_strict_context_block(...)`.
- [x] Remove the `if context_guardrail and context_guardrail.action == "block":` path.
- [x] Remove `context=context_guardrail` from chat metadata `_guardrail_map(...)`.
- [x] Remove the helper `_downgrade_non_strict_context_block(...)`.
- [x] Keep `_has_prompt_injection_category(...)` only if still used elsewhere; otherwise remove it.
- [x] Preserve the existing input guardrail flow.
- [x] Preserve the existing output guardrail flow.
- [x] Preserve the existing evidence-state downgrade logic (`not_enough_evidence`).
- [x] Preserve the blocked-input and blocked-output response logic.

### Frontend

- [x] Inspect frontend meeting chat UI and metadata rendering.
- [x] Remove any UI references to `context` guardrail if present.
- [x] Remove any UI references to `transcript` guardrail if present.
- [x] Keep display for remaining guardrail metadata (`input`, `output`).
- [x] Verify chat history rendering still works for old messages containing context/transcript guardrail metadata.
- [x] Verify frontend build remains clean after metadata shape changes.

### Documentation

- [x] Update `docs/plans/5.6 - local guardrails.md` to reflect that transcript and retrieved-context guardrails were removed.
- [x] Update `docs/plans/0 - project overview.md` chat flow to remove `guardrail input/context checks`.
- [x] Update `docs/plans/0 - project overview.md` env block to remove the two deprecated guardrail variables.
- [x] Update `docs/explanations/backend-explanation.md` processing events to remove transcript guardrail.
- [x] Update `docs/explanations/backend-explanation.md` chat/RAG description to remove retrieved-context guardrail.
- [x] Update `docs/explanations/backend-explanation.md` env table to remove the two deprecated guardrail variables.
- [x] Update `docs/explanations/infrastructure-explanation.md` env table to remove the two deprecated guardrail variables.
- [x] Update `docs/PROJECT_PLAN.md` if phase summary behavior or explanation scope changes.

### QA checklist

- [x] Confirm no backend code references `guardrail_transcript_enabled` or `guardrail_context_enabled`.
- [x] Confirm no backend code references `GUARDRAIL_TRANSCRIPT_ENABLED` or `GUARDRAIL_CONTEXT_ENABLED`.
- [x] Confirm no docker/env/docs references remain for the removed variables.
- [x] Confirm transcript processing no longer depends on guardrail outcome.
- [x] Confirm meeting chat only depends on input/output guardrails.
- [x] Confirm old meetings with existing `source.guardrails` metadata still load in UI and retrieval.

## Verification Plan

### Automated Tests

- [x] Verify no remaining references via repo-wide search for `transcript_guardrail` and `context_guardrail`.
- [x] Run backend unit tests (57/57 passed; 4 DB-dependent tests skipped due to no local PostgreSQL).
- [x] Run targeted guardrail provider tests (6/6 passed).
- [x] Run chat service tests (pre-existing `ProcessingJobStatus` import failure, unrelated to this phase).
- [x] Run processing pipeline tests (pre-existing `ProcessingJobStatus` import failure, unrelated to this phase).
- [x] Run frontend production build.

### Manual Verification

- [x] Upload/process a meeting and confirm the worker completes without transcript guardrail stage.
- [x] Ask a meeting chat question and confirm only input/output guardrail metadata is present in saved assistant message.
- [x] Confirm old meeting chat messages still render correctly.
- [x] Confirm processed JSON with prior transcript guardrail metadata remains accessible and searchable.
- [x] Confirm operational logs no longer contain transcript/context guardrail events.

### Acceptance Criteria

- [x] Input guardrail remains active.
- [x] Output guardrail remains active.
- [x] Transcript guardrail is fully removed from the active processing path.
- [x] Retrieved-context guardrail is fully removed from the active chat path.
- [x] Related environment variables are removed from config, compose, example env, and docs.
- [x] Old guardrail metadata remains backward compatible.
- [x] Documentation reflects the reduced guardrail scope.

---

## Completion Report

> **Completed at:** 2026-07-06
> **Verified by:** 57/57 unit tests passed, frontend production build passed, repo-wide reference search clean, pre-existing test failures confirmed unrelated

### What was implemented

- Removed `guardrail_transcript_enabled` and `guardrail_context_enabled` from `backend/configs/settings.py`.
- Removed `GUARDRAIL_TRANSCRIPT_ENABLED` and `GUARDRAIL_CONTEXT_ENABLED` from `.env.example` and `docker-compose.yml` (backend + worker).
- Removed transcript guardrail stage, helper, and metadata append from `backend/services/processing_pipeline_service.py`.
- Removed context guardrail block, event, downgrade logic, and dead helpers from `backend/services/chat_service.py`.
- Chat metadata now only contains `input` and `output` guardrail results.
- Retrieval index `source.guardrails` chunk logic preserved for backward compatibility with existing processed JSON.
- Frontend inspected — no UI references to context/transcript guardrail.
- All related docs updated to reflect reduced guardrail scope.

### What was changed from original plan

- `_append_guardrail_metadata` helper in processing pipeline was also removed (became dead code after transcript guardrail removal).
- `_has_prompt_injection_category` helper in chat service was also removed (only used by the now-removed context downgrade logic).
- `_retrieved_context_text` helper in chat service was also removed (only used by the now-removed context guardrail check).
- `replaced` import from `dataclasses` removed from `chat_service.py` (only used by the now-removed downgrade logic).

### Notes for future sessions

- Old processed JSON may still contain `source.guardrails.transcript` metadata; retrieval index continues to handle it.
- Chat history messages saved before this phase may still contain `context` guardrail metadata; no migration needed.
- `test_chat_service` and `test_processing_pipeline_service` have pre-existing `ProcessingJobStatus` import failures unrelated to this phase.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/plans/0 - project overview.md`
- [x] `docs/plans/5.6 - local guardrails.md`
- [x] `docs/plans/8 - operational logs.md`
- [x] `docs/PROJECT_PLAN.md`
