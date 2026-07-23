# Phase 47 - Direct Cutover To Simple Evidence-First RAG

## Status: In Progress

## Objectives

1. Replace the old chat runtime with one linear `simple-rag.v1` pipeline.
2. Make `QuerySpec`, `EvidenceBundle`, LLM synthesis, and mandatory terminal verification the only successful-answer path.
3. Remove Agentic RAG orchestration, answer/semantic cache, Agent Memory, and old diagnostics from source/runtime.
4. Reset and reprocess the two accepted meetings only after backup, test, provider, security, and golden-corpus gates pass.
5. Roll back by previous images/git revision and a restore-tested PostgreSQL backup; no legacy/shadow/canary runtime mode exists.

## Canonical Flow

```text
Request gate
-> QuerySpec
-> Retrieval plan
-> EvidenceBundle
-> Evidence validation
-> LLM synthesis
-> Answer verification
-> Output policy
-> Persistence
```

Successful `direct`, `grounded`, and `partial` answers require `answerOriginKind=llm_synthesis`. Clarification, `not_enough_evidence`, blocked, and error/control responses are fixed and do not call answer synthesis.

## Implementation Checklist

### 1. QuerySpec

- [x] Add immutable `QuerySpec`, `GoalSpec`, and trusted typed reference contracts.
- [x] Use one deterministic-first `QueryInterpretationService` for Vietnamese/English direct, summary, count, list, contact, action, decision, risk, date, and location intents.
- [x] Reconstruct follow-up anchors only from backend-authored typed metadata and durable message IDs.
- [x] Keep explicit current-meeting overview questions self-contained; they cannot inherit a prior direct-intent target from history.
- [x] Resolve language from client locale or `DEFAULT_CHAT_LANGUAGE`, never question text; classify reusable intent concepts so both meeting-subject phrasings are the same standalone summary intent.
- [x] Return clarification when a contact entity or trusted history anchor is missing.
- [x] Remove QueryGraph/resolver/interpreter/planner cascade and old intermediate query models from production.
- [ ] Expand the golden corpus from semantic-operation checks to transcript-reviewed expected facts, completeness, and references.

### 2. Deterministic retrieval

- [x] Add one `EvidenceRetrievalService` receiving only `QuerySpec` and the ready snapshot.
- [x] Plan structured-first retrieval deterministically and fall back to semantic retrieval only when structured results are absent.
- [x] Keep direct intents retrieval-free and multi-goal plans goal-scoped.
- [x] Remove model-driven tools, registry, executor, replan, and parallel tool orchestration.
- [x] Stop indexing quality/extraction warnings and evidence-map operational metadata as factual search content.
- [x] Keep whole-meeting summaries on verified summary evidence or transcript fallback only; never promote an individual extracted record to the meeting topic.
- [ ] Add fixture coverage proving whole-summary-first behavior and coverage-aware per-goal context budgeting.

### 3. EvidenceBundle

- [x] Add immutable per-goal bundles, typed facts, transcript excerpts, refs, status, missing fields, meeting ID, and snapshot generation.
- [x] Adapt PostgreSQL/search records at the retrieval boundary; downstream services receive bundles only.
- [x] Reject duplicate refs, stale-generation records, and refs without transcript segment lineage.
- [x] Persist only a bounded, redacted bundle projection in `pipelineTrace v1`.
- [ ] Add property tests for cross-meeting and cross-generation adapter inputs.

### 4. Meeting intelligence quality

- [x] Validate evidence references before persistence and remove records lacking valid refs.
- [x] Prevent an identical unsupported statement from surviving as both action and decision.
- [x] Build executive summary lineage from all processed windows with `coveredWindowIds`, `coverageRatio`, sentence refs, and `lineageStatus`.
- [x] Mark incomplete summaries `context_only` and keep them out of factual evidence.
- [x] Keep deterministic opening-snippet summary fallback `context_only`; it cannot be promoted to whole-meeting evidence by window-count arithmetic.
- [x] Keep participant-count derivation separate from generic provider claims.
- [ ] Complete transcript-reviewed semantic entailment audits for actions, decisions, risks, topics, and questions on both cutover meetings.

### 5. LLM-only successful answers

- [x] Add `SynthesisContract` with language, goals, locked facts, allowed refs, direct intent, and disclosure permissions.
- [x] Keep citation IDs backend-owned: model claims select fact IDs only; verifier derives authoritative refs from the matching EvidenceBundle.
- [x] Keep broad summaries free of profile/contact disclosure unless the QuerySpec explicitly requests an authorized field; record actual output-policy block categories in `pipelineTrace`.
- [x] Treat an answer in the wrong requested script as contract-invalid and use the single synthesis retry before terminal error.
- [x] Require JSON `{answer, claims}` and retry a contract-invalid response exactly once.
- [x] Retry the effective provider that succeeded at transport; do not contract-retry transport failures.
- [x] Remove deterministic business-answer renderers and structured-projection terminal answers.
- [x] Route direct intents through LLM synthesis and output guardrail.
- [ ] Verify all live direct/grounded/partial outcomes report `llm_synthesis` across both providers.

### 6. Mandatory answer verification

- [x] Add a non-configurable `AnswerVerificationService` as terminal authority.
- [x] Validate goals, facts, refs, fact-to-ref ownership, goal isolation, locked values, and current snapshot generation.
- [x] Map UI citations only from verified refs with per-citation segment/timestamp lineage.
- [x] Return error/control after the second contract failure.
- [ ] Extend complete-list and partial-completeness property coverage.

### 7. Provider and deadline contract

- [x] Disable Qwen hidden thinking with `chat_template_kwargs.enable_thinking=false` when `LLM_REASONING_MODE=disabled`.
- [x] Classify `content=null`, truncated JSON, or `finish_reason=length` from OpenAI-compatible/Ollama adapters as `llm_output_exhausted`.
- [x] Remove the old five-second primary cap and wire 15/20/60/40/15/150 second budgets.
- [x] Separate LLM circuit state by stage/provider/model and log effective provider/model/latency/finish reason/error.
- [x] Preserve primary and fallback failure provenance.
- [x] Run live minimal JSON on primary/Ollama, full primary synthesis, and forced-primary-failure Ollama synthesis against the candidate source/image contract.
- [ ] Run live timeout and both-provider-failure lifecycle probes through the final worker/API path.

### 8. Security and output policy

- [x] Redact OpenAI, NVIDIA, JWT, bearer, password, and generic credential shapes before input persistence and trace publication.
- [x] Bypass model output guardrail for fixed control responses.
- [x] Fail closed with explicit error state when the guardrail provider fails.
- [x] Run all LLM-produced direct/meeting output through `OutputPolicyService`.
- [ ] Rotate the previously exposed NVIDIA key outside the repository.
- [ ] Scan PostgreSQL, Redis, and operational logs after reset and live replay for raw test credentials.

### 9. Remove cache and memory

- [x] Delete Answer Cache/Semantic Cache/singleflight services, settings, metrics, Redis keys, and chat dependencies.
- [x] Delete Agent Memory service, injection, revalidation tasks, queues, beat routes, and source model wiring.
- [x] Collapse the Alembic tree to the single baseline `0001_initial_schema` and remove obsolete revision files.
- [x] Rebuild the local database from `0001_initial_schema` only.
- [x] Preserve feedback ratings with `memory_status=disabled` and `cache_action=disabled` and no pipeline side effects.
- [x] Remove frontend/admin cache-memory diagnostics.

### 10. Layered services and old-pipeline deletion

- [x] Limit `MeetingChatService` to authorization, turn/lease lifecycle, policy orchestration, and persistence.
- [x] Isolate query, retrieval, synthesis, verification, and output-policy services under `backend/services/simple_rag/`.
- [x] Keep repositories data-only and provider adapters transport-only.
- [x] Reduce Celery chat task ownership to resolving the service and executing a durable turn.
- [x] Delete old Agent loop/context/query graph/planner/tool/synthesizer modules and imports.
- [x] Remove old runtime settings, Compose wiring, startup summaries, tasks, and tests.

## Runtime Settings

The following keys exist in `.env`, `.env.example`, typed settings, and backend/worker Compose environments:

| Setting | Default | Purpose |
|---|---:|---|
| `DEFAULT_CHAT_LANGUAGE` | `en` | Fallback locale when the client omits BCP 47 `language` |
| `RAG_QUERY_INTERPRETATION_TIMEOUT_SECONDS` | `15` | QuerySpec stage budget |
| `RAG_EVIDENCE_RETRIEVAL_TIMEOUT_SECONDS` | `20` | Retrieval and bundle budget |
| `RAG_SYNTHESIS_PRIMARY_TIMEOUT_SECONDS` | `60` | Primary answer-generation budget |
| `RAG_SYNTHESIS_FALLBACK_TIMEOUT_SECONDS` | `40` | Fallback answer-generation budget |
| `RAG_FINALIZATION_RESERVE_SECONDS` | `15` | Reserved verification/policy/persistence time |
| `RAG_CHAT_TURN_TIMEOUT_SECONDS` | `150` | End-to-end turn deadline |
| `RAG_SYNTHESIS_CONTRACT_RETRIES` | `1` | Exactly one validation retry |
| `LLM_REASONING_MODE` | `disabled` | Disable hidden Qwen thinking |
| `CHAT_TURN_LEASE_SECONDS` | `300` | Durable worker lease and redelivery fence |

Contract versions are source constants, not runtime knobs: `simple-rag.v1`, `simple-retrieval.v1`, `query-spec.v1`, `evidence-bundle.v1`, `synthesis-contract.v1`, and `answer-verification.v1`.

## Diagnostics

- [x] Remove `agentFlow` and `agentRawFlow` from backend/frontend public contracts.
- [x] Add `pipelineTrace v1` with request gate, query interpretation, retrieval, evidence validation, synthesis, answer verification, output policy, and persistence stages.
- [x] Persist terminal trace stages into Admin RAG operational logs, including contract-verification failures.
- [x] Bound/redact stage details and exclude prompts and hidden reasoning.
- [x] Make chat SSE turn-scoped with durable latest-stage replay; stream the actual Simple RAG stages and terminal persisted assistant payload.
- [x] Replace old Flow/Trace/Full Raw UI with `PipelineTraceViewer` while retaining citations/evidence badges.
- [x] Keep public chat endpoints and durable SSE/history lifecycle unchanged.

## Backup, Reset, And Reprocess

### Completed safety work

- [x] Create timestamped PostgreSQL custom dump.
- [x] Export meeting asset metadata, MinIO inventory, intelligence fixtures, git revision, and previous image IDs.
- [x] Restore the dump into an isolated PostgreSQL database and verify meeting/asset counts.
- [x] Add `backend/scripts/direct_cutover_reset.py` with exact meeting allowlist, dry-run default, required backup directory, and explicit `--execute`.
- [x] Preserve meeting rows, ownership, assets, and source audio by design.

### Pending destructive/runtime work

- [ ] Run the reset script in dry-run mode against final images and review every target.
- [ ] Delete derived chat/transcript/intelligence/snapshot/chunk/vector/temporary key state for the two approved meetings.
- [ ] Requeue processing from source audio and rebuild intelligence, whole summary, PostgreSQL chunks, Milvus vectors, and retrieval snapshot.
- [ ] Return each meeting to `READY` only when validation/indexing pass and PostgreSQL/Milvus generations match.
- [ ] Record reset execution, new generations, and reprocessing durations in the completion report.

## Verification Status

### Passed

- [x] Python compile/import check.
- [x] Compose configuration validation.
- [x] Core Simple RAG/provider/retrieval/intelligence regression: `44/44`.
- [x] Full backend discovery from the final candidate image on isolated restored PostgreSQL/Redis with no-op vector adapter: `191/191`.
- [x] Frontend regression: `37/37`.
- [x] Frontend production build.
- [x] Build candidate backend, worker, beat, and frontend images and record their digests beside rollback metadata.
- [x] Alembic upgrade to single head `0001_initial_schema` on the cleaned local database.
- [x] Static production-source scan for old Agentic RAG/cache/memory imports.

### Strict gates still pending

- [ ] Transcript-reviewed 60 single-turn and 20 multi-turn golden expectations, followed by 100% live replay.
- [ ] Live primary, Ollama fallback, both-provider failure, timeout, and contract retry matrix.
- [ ] API -> RabbitMQ -> worker -> PostgreSQL -> SSE/history/feedback acceptance on final images.
- [ ] Worker redelivery/lease fencing and snapshot-change acceptance.
- [ ] Credential scans with zero raw matches after reset/replay.
- [ ] Full derived reset and reprocess of both approved meetings.
- [ ] Final backend/worker/beat/frontend image builds, digests, deploy, health checks, and smoke corpus.

## Rollback

- [x] Record previous backend, worker, and frontend image identifiers and previous git commit in the backup directory.
- [x] Keep source audio in MinIO outside derived reset scope.
- [x] Validate PostgreSQL restore before allowing destructive reset.
- [ ] Record final new image digests before deploy.
- [ ] Execute and verify the operator rollback runbook against final artifacts.

Rollback never re-enables old source code in the new image. Before new durable data, redeploy previous images. After an incompatible reset/migration, restore the tested PostgreSQL dump and rebuild Milvus from restored intelligence.

## Acceptance Criteria

- [ ] Every successful direct/grounded/partial answer originates from LLM synthesis.
- [ ] Zero unsupported grounded claims, invalid citations, cross-goal evidence, or locked-fact drift.
- [ ] Zero provider contract errors and zero raw credential leaks.
- [ ] Every turn terminates within 150 seconds with at least 15 seconds reserved for finalization.
- [ ] Both cutover meetings are `READY` on matching new retrieval generations.
- [ ] Full golden corpus and post-deploy smoke corpus pass on final image digests.

## Completion Report

Pending. Phase 47 must remain `In Progress` until all strict runtime gates, destructive reset/reprocessing, direct deploy, and smoke verification are complete.

### Related docs

- [x] `README.md`
- [x] `docs/plans/0 - project overview.md`
- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
