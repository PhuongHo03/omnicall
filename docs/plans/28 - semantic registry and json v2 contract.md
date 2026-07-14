# Phase 28 - Semantic Registry and JSON v2 Contract

## Status: Done

## Objectives

1. Define a code-owned vocabulary for generalized `knowledge.records`.
2. Keep LLM-discovered subtypes in record payloads instead of creating uncontrolled top-level schemas.
3. Preserve unknown valid observations through a generic fallback type.

## Tasks

### Semantic registry

- [x] Add canonical record families for participants, entities, facts, events, topics, actions, decisions, risks, questions, relationships, and observations.
- [x] Add alias normalization for common LLM labels.
- [x] Keep subtype names such as `participant_count` inside the payload.
- [x] Add `observation` fallback for unknown record types.

### Contract boundary

- [x] Add a dedicated `backend.services.knowledge` domain module.
- [x] Add unit tests proving canonicalization and fallback behavior.
- [x] Define the v2 envelope fields for evidence references, source references, derivation, and record provenance.
- [x] Remove v1 field names from the runtime reducer and validator during the v2 cutover phases.

## Verification Plan

### Automated Tests

- [x] `python3 -m unittest backend.tests.knowledge.test_semantic_registry`
- [x] Run processing/retrieval groups in container and full backend discovery; targeted contract groups pass.

### Acceptance Criteria

- [x] No LLM-generated type can create an unregistered top-level record family.
- [x] Unknown types remain queryable as `observation` records.
- [x] The v2 record envelope is runtime-validated by a dedicated contract module.
- [x] The persisted processable results use only the v2 evidence/provenance contract.

## Completion Report

> **Completed at:** 2026-07-14
> **Verified by:** `python3 -m unittest backend.tests.knowledge.test_semantic_registry`; `python3 -m compileall -q backend/services/knowledge backend/tests/knowledge`; `git diff --check`

### What was implemented

- Added a code-owned semantic registry and alias normalization.
- Added the v2 knowledge record envelope builder and shape validator.
- Added fallback handling for unknown LLM concepts as `observation` records.

### What changed from original plan

- Runtime persistence remains v1 until the reducer/evidence migration phases complete; no compatibility adapter was introduced.

## Related Docs

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
