# Phase 21 - Fast Path Temperature Tuning

## Status: Done

## Objectives

1. Make fast-path chat answers less repetitive for greetings and small talk.
2. Keep structured LLM JSON flows deterministic by default.
3. Ensure primary/fallback LLM providers pass temperature consistently.

## Prerequisites

- [x] Current fast-path flow is understood.
- [x] LLM provider default `temperature: 0` behavior is confirmed.

## Tasks

### 1. Provider Contract

- [x] Add optional `temperature` to `LLMProvider.generate_json`.
- [x] Add optional `temperature` to `LLMProvider.generate_stream_json` for consistency.
- [x] Keep default temperature at `0`.
- [x] Pass temperature through OpenAI-compatible, custom endpoint, Ollama, and fallback providers.

### 2. Fast Path

- [x] Add a fast-path-specific temperature constant.
- [x] Use the fast-path temperature only when calling `FastPathHandler`.
- [x] Keep RAG planning, answer synthesis, and analysis calls on the default deterministic temperature unless explicitly changed later.

### 3. Tests

- [x] Update fake LLM provider signatures.
- [x] Add coverage that fast path passes the configured temperature.
- [x] Add coverage that fallback provider forwards temperature to primary and fallback providers.

## Verification Plan

### Automated Tests

- [x] `docker compose exec -T backend python -m unittest backend.tests.test_fast_path_handler backend.tests.test_llm_provider`
- [x] `docker compose exec -T backend python -m unittest backend.tests.test_agentic_rag_service`

### Manual Verification

- [x] Source review confirms only fast path changes temperature.

### Acceptance Criteria

- [x] Fast path uses non-zero temperature.
- [x] Default LLM JSON behavior remains temperature `0`.
- [x] Tests pass.

---

## Completion Report

> **Completed at:** 2026-07-09
> **Verified by:** backend py_compile, `docker compose exec -T backend python -m unittest backend.tests.test_fast_path_handler backend.tests.test_llm_provider`, and `docker compose exec -T backend python -m unittest backend.tests.test_agentic_rag_service`.

### What was implemented

- Added optional per-call `temperature` to the LLM provider JSON contract and implementations while preserving default `0`.
- Forwarded temperature through `FallbackLLMProvider` for primary and fallback paths.
- Set `FastPathHandler` to call the LLM with `temperature=0.5` for direct non-RAG responses.
- Added tests for fast-path temperature, OpenAI-compatible custom temperature, and fallback temperature forwarding.

### What was changed from original plan

- Host `python3` could parse the touched files but could not run tests because local dependencies such as `pydantic` and `sqlalchemy` are not installed; tests were run in the backend container instead.

### Notes for future sessions

- Keep structured analysis/planning/synthesis calls on default `temperature=0` unless a future phase intentionally tunes them.
- If custom JSON endpoints reject unknown `temperature`, adapt the endpoint adapter to omit or rename that field per endpoint contract.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md` (phase summary table)
