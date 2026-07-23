# Phase 39 - Agentic RAG v2 alignment

## Status: Done

## Objectives

Make planner, retrieval tools, verifier, context, and synthesizer consume the JSON v2 `knowledge.records` and `evidence.items` contract as their primary boundary.

This phase also makes `knowledge.records` the only intelligence collection: transcript speaker labels remain source data, while speaker profiles and statistics become participant/fact records.

## Tasks

### Planner and selectors
- [x] Emit canonical `recordTypes` and `recordSubtypes` in plans and replans.
- [x] Use record selectors as the primary retrieval route when a plan targets knowledge records.
- [x] Keep section selectors only for v2 top-level projections such as summaries and operational metadata.

### Tools and context
- [x] Make `search_records` support multiple canonical types/subtypes.
- [x] Convert specialized action, decision, risk, timeline, and participant tools into v2 selector presets.
- [x] Carry record identity, payload fields, evidence refs, source refs, and derivation metadata into agent context.

### Verification and synthesis
- [x] Verify relevance against canonical record types before section labels.
- [x] Verify required fields against record payload metadata and evidence refs.
- [x] Accept only evidence refs supplied by context and map them to UI citations safely.
- [x] Expose verified evidence refs in answer metadata.
- [x] Reject v1 evidence collections and non-v2 retrieval indexing inputs instead of silently adapting them.
- [x] Move deterministic speaker profiles and speaker counts into `knowledge.records`.
- [x] Remove specialized speaker/participant/action/decision/risk/timeline tools from the LLM catalog; use generic selectors.
- [x] Remove persisted top-level `speakers` from the v2 reducer and validation contract.
- [x] Persist `recordId`/provenance metadata on participant chunks so `search_records` can retrieve them.
- [x] Prevent full natural-language planner queries from filtering out type-selected records.
- [x] Replace the remaining provider-side v1 candidate contract with explicitly named `meeting-intelligence-candidate.v2`; persisted output remains `meeting-intelligence-result.v2`.

## Verification Plan

- [x] `python3 -m compileall -q backend`
- [x] `git diff --check`
- [x] Run the Agentic RAG backend test suite in the backend test environment (`131 tests OK`).
- [x] Validate v2 record/evidence metadata paths with generalized evidence fixtures and source compilation.
- [x] Run `python -m backend.scripts.verify_v2_cutover` (`1 meeting, 1 processable v2 result, 100 chunks, 1 identity relationship, 0 orphan chunks, 0 failures`).
- [x] Reprocess existing local meetings with the migrated reducer and verify their persisted JSON has no top-level `speakers`.
- [x] Scan and remove all active v1 provider constants and v1 fixtures after candidate-contract migration.

## Completion Report

> **Completed at:** 2026-07-15
> **Verified by:** backend unittest discovery, v2 cutover verifier, persisted JSON audit, frontend production build, Python compileall, and git diff check

### Notes

The v2 contract remains authoritative. Existing section names are retained only where the persisted v2 document has a top-level projection that is not a knowledge record.

The final runtime audit reports `meetings=1`, `processable=1`, `v2Results=1`, `chunks=100`, `identityRelationships=1`, `orphanChunks=[]`, and `failures=[]`. The persisted result has no top-level `speakers`; speaker profiles and counts are canonical records.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/plans/0 - project overview.md`
