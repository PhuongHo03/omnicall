# Phase 44 - Context-aware verified RAG orchestration

## Status: Done

## Objectives

1. Resolve meeting-scoped conversational references into one canonical question before planning, retrieval, cache, and memory selection.
2. Make chat work durable and idempotent while allowing only one active turn per meeting.
3. Serve only current-snapshot, claim-verified answers from cache and keep Agent Memory limited to verified retrieval-strategy hints.
4. Remove raw reasoning and internal orchestration state from public chat contracts.

## Prerequisites

- [x] Phase 39 v2 alignment is verified against persisted `knowledge.records`/`evidence.items` data with no top-level `speakers` projection.
- [x] Phase 40 generic query graph and answer projections are Done.
- [x] Phases 41-43 remain historical Done milestones; Phase 44 replaces how their capabilities are orchestrated.

## Tasks

### 44A - Safety and durable foundations

- [x] Add additive migrations `0005`-`0008` for durable chat turns, authoritative retrieval snapshots, revisioned feedback/memory compatibility, turn leases, legacy lifecycle repair, and durable vector-repair claims.
- [x] Backfill legacy user/assistant messages without deleting chat, citations, results, chunks, or feedback; classify pending/orphan legacy turns as terminal errors instead of prompt history.
- [x] Enforce one `queued`/`started` turn per meeting and return `409 chat_busy` for a concurrent chat request.
- [x] Make workers consume persisted turn identity, claim work through a lease token, and fence terminal writes with the claimed lease so redelivery/takeover is idempotent.
- [x] Keep queued/stale turns and pending feedback recoverable through reconciliation when broker publication or a worker attempt fails.
- [x] Make `meeting_retrieval_snapshots` authoritative for generation, embedding identity, retrieval contract, chunk count, and repair lifecycle.
- [x] Renew Redis processing locks with an ownership-checked Lua heartbeat and stop stale workers from writing after ownership is lost.
- [x] Remove persisted `agentThoughts` from legacy metadata, stop generating/persisting raw reasoning, and expose chat metadata through an explicit public allowlist.
- [x] Pass bounded Phase 41-44 settings to both backend and worker; validate values and log only the effective non-secret configuration.

### 44B - Context-aware retrieval and grounding

- [x] Add immutable `RAGRequestContext` carrying raw/canonical questions, dependency mode, referents, entity/context fingerprints, query constraints, snapshot identity, and structured conversation context.
- [x] Load only completed paired turns before the current turn; filter pending, blocked, error, clarification, and orphan messages before applying the 6-turn/1,200-token limits.
- [x] Preserve at most six complete citation IDs per prior assistant message and serialize history as untrusted JSON data.
- [x] Run input guardrails on the raw question and again after a canonical rewrite.
- [x] Resolve conversational references with a bounded resolver (`0.85` confidence, `15s` timeout); persist `clarification_needed` without calling retrieval/cache/memory when resolution is ambiguous.
- [x] Use the canonical question throughout fast path detection, query planning, tool execution, retrieval fallback, synthesis, cache, and memory matching.
- [x] Keep history out of current-snapshot factual evidence. After reference resolution, request-scoped Agentic RAG receives the canonical question rather than replaying history into planning/synthesis.
- [x] Support `LLM_PROMPT_DATA_POLICY=trusted|redact` with request-stable allowlisted placeholders for external LLM data.
- [x] Require synthesis claims to cite freshly retrieved evidence references; deterministically verify claim anchors, remove unsupported claims or downgrade to `partial`, and return `not_enough_evidence` when no claim remains supported.
- [x] Relevance-rank type-selected generic records without filtering them out, normalize Vietnamese/English query aliases, prefer directly evidenced records on ties, and version both tool-catalog and verifier contracts in the pipeline fingerprint.
- [x] Continue safely without history, memory, embedding cache, Redis, or optional provider data when those dependencies fail.

### 44C - Cache v2

- [x] Add owner/meeting/generation/pipeline-scoped embedding, retrieval, and answer cache layers in Redis.
- [x] Key exact answers by canonical question plus intent, answer shape, entity, negation, temporal, locale, and contextual referent fingerprint.
- [x] Rehydrate cached chunk/citation IDs from authoritative PostgreSQL data and validate generation, pipeline, answer/integrity hashes, cache lifecycle, and guardrail policy before serving.
- [x] Quarantine a rejected or corrupt cache candidate and fall back to Agentic RAG instead of returning a cache-induced blocked response.
- [x] Admit only grounded, cited, claim-verified answers that passed output guardrails; exclude fast path, partial, blocked, error, clarification, and insufficient-evidence responses.
- [x] Use 24-hour normal and 7-day verified TTLs, a bounded 100-entry meeting index, atomic Redis storage/trim, and a short singleflight lock.
- [x] Double-check the retrieval snapshot before both serving and storing; use logical invalidation plus best-effort physical cleanup for reindex/reprocess, deletion, and feedback changes.
- [x] Keep Redis and cache corruption fail-open to the normal RAG path.

### 44D - Verified Agent Memory v2 and feedback lifecycle

- [x] Persist only allowlisted strategy fields: intent, answer shape, sanitized selectors/relations/filters, evidence-contributing successful tools, result counts, and retrieval identities.
- [x] Exclude raw reasoning, answer text, chunks, citation content, raw subqueries, and full internal plans from Agent Memory.
- [x] Match only active memory from the same meeting, generation, embedding identity, retrieval contract, pipeline, context, intent, answer shape, and entity set before cosine similarity `>=0.92`.
- [x] Select deterministically at most three hints from at most 100 active candidates; hints may extend retrieval but cannot skip base retrieval, verification, guardrails, or citations.
- [x] Mark memory stale on index changes and revalidate allowlisted strategy calls against the current snapshot before reactivation.
- [x] Make feedback revision-aware and persist `up`, `down`, and `neutral`; stale worker revisions cannot overwrite the latest user choice.
- [x] Require `up + grounded + citations + claim verification + successful strategy lineage` before creating memory; cache-only answers cannot create empty memory.
- [x] Make `down`/`neutral` deactivate related memory and logically invalidate or quarantine the relevant cache mapping.
- [x] Keep per-message UI pending state, disable both controls during a request, toggle the selected button to neutral, rollback on error, and hydrate the persisted rating/revision after refresh.

### 44E - Semantic cache shadow/canary safety

- [x] Default semantic mode to `shadow`, threshold `0.94`, observed precision `0.0`, and canary `0%`; exact cache remains independently enabled.
- [x] Record semantic candidates and hard negatives for intent, answer shape, entity, negation, time, locale, and context mismatches without directly serving shadow candidates.
- [x] Gate direct semantic serving on verified-tier entries, current citations/contracts, observed precision `>=99%`, and deterministic canary assignment.
- [x] Provide an immediate `canary -> shadow -> off` runtime kill switch.
- [x] Keep direct semantic serving disabled in the verified runtime (`shadow`, canary `0%`) until an offline shadow dataset demonstrates at least 99% precision. Promotion to 5% is an operational rollout gate, not a completed-runtime claim in this phase.

### API, UI, security, and observability

- [x] Keep the chat request contract additive; add `409 chat_busy`, `clarification_needed`, SSE `clarification`, and a persisted terminal assistant payload.
- [x] Return top-level `feedback_rating`/`feedback_revision` and an authoritative feedback response while retaining compatibility mapping for older metadata for one release.
- [x] Hide feedback controls for streaming, blocked, error, fast-path, and clarification messages; expose accessible `aria-pressed`/disabled controls for eligible terminal answers.
- [x] Keep raw thoughts, full plans/tool arguments, memory IDs, token internals, Redis keys, and internal errors out of public API/browser state.
- [x] Add sanitized logs and bounded-label Prometheus metrics for context, resolver, cache, claim verification, memory lifecycle, durable turns, reconciliation, and busy rejection.

### Independent completion-audit hardening

- [x] Reject directional claim role reversal using structured actor/target fields first and bounded English/Vietnamese active/passive text fallback; bump the verifier cache contract.
- [x] Keep Vietnamese `họ tên` and uppercase `IT` standalone while preventing a real unresolved pronoun from being downgraded by an LLM; bump the resolver cache contract.
- [x] Replace finite-list-only dependency gating with open-vocabulary classification for every question that has completed conversation history; fail closed to `clarification_needed` when dependency cannot be established safely.
- [x] Make the backend construct canonical questions from exact source/replacement spans in the raw question, so provider output cannot reorder actor, action, target, negation, or time; bump the resolver pipeline contract to `conversation-resolver.v4-structural-rewrite`.
- [x] Require Agent Memory query embeddings to match the authoritative snapshot embedding identity, including fallback embeddings and caller-supplied vectors.
- [x] Move active memory to `stale` on every rebuild with a prior snapshot, including retrieval-contract-only changes whose generation hash is unchanged.
- [x] Make exact cache-hit `neutral` deactivate source-lineage memory as well as invalidating the source cache lifecycle.
- [x] Make singleflight contention wait briefly and recheck exact cache before duplicate Agent execution, while retaining fail-open behavior.
- [x] Sanitize every SSE event at the DTO boundary, filter public tools again in the watcher, and reject malformed/private terminal payload fields.
- [x] Preserve pending or higher-revision feedback during every history refresh and render accessible `chat_busy`, feedback-error, and notice messages.
- [x] Replace the meeting-local notice with one top-center App Shell toast shared by meeting/admin routes; preserve create/record/delete notices across selection changes, keep clarification solely in the persisted live-region chat bubble, use the authoritative refreshed meeting state to distinguish `Chat refreshed.` from `Status refreshed.`, and keep Admin toast output limited to explicit Refresh actions.
- [x] Keep local `.env` and tracked `.env.example` key surfaces aligned and verify the same bounded Phase 44 settings in backend/worker Compose output.

## Verification Plan

### Automated tests

- [x] Full backend unittest discovery passes (`342 tests OK` after the resolver-v4 completion audit hardening).
- [x] History/resolver tests cover completed-turn filtering, limits, meeting isolation, paired messages, common and open-vocabulary references, complete-phrase binding grounding, distinct referent fingerprints, backend-owned structural rewrite, actor/target reversal, ambiguity, timeout/provider failure, and prompt-data safety.
- [x] Chat/cache tests cover busy rejection, idempotent lease fencing, exact/context signatures, semantic hard negatives, corrupt/stale/Redis fallback, generation races, rehydration, admission, invalidation, and atomic limits.
- [x] Claim-verifier tests cover unknown references, lexical/number/entity/predicate anchors, negation, partial answers, and current-evidence-only grounding.
- [x] Memory/feedback tests cover eligibility, strategy sanitation, contract gates, stale revalidation, revision ordering, `up`/`down`/`neutral`, cache-hit lineage, and failure fallback.
- [x] Processing/repair tests cover lock renewal/loss and durable vector-repair claim, retry, stale recovery, and duplicate-delivery behavior.
- [x] Frontend Vitest/React Testing Library suite passes (`28 tests` across `10` files) and production build succeeds (`1,792` modules transformed), including global toast timing/accessibility, single-path Refresh, and persisted SSE clarification rendering.
- [x] Dedicated Redis integration suite passes (`4 tests`), including atomic trim and singleflight ownership/wait behavior.

### Migration and runtime verification

- [x] Upgrade a seeded legacy database from `0004` through `0008`, verify messages/results/chunks/feedback are preserved and raw thoughts removed, downgrade to `0005`, then re-upgrade to head.
- [x] Confirm the active database is at `0008_vector_repair_claims` and the runtime retrieval snapshot is `ready` with contract `v2`.
- [x] Inspect Compose configuration and startup logs to confirm Phase 41-44 defaults reach backend and worker; semantic direct serving remains `shadow`/`0%`.
- [x] Confirm `.env` and `.env.example` expose identical key sets and deploy freshly built backend, frontend, worker, and beat images with healthy services.
- [x] Run `verify_v2_cutover`: `meetings=1`, `processable=1`, `v2Results=1`, `chunks=100`, `identityRelationships=1`, `orphanChunks=[]`, `failures=[]`.
- [x] Verify persisted v2 JSON contains zero top-level `speakers` keys and legacy chat metadata contains zero `agentThoughts` keys.
- [x] On meeting `87ab3e7a-45ee-4d21-97de-2aed7673e746`, ask `Ai là khách hàng?` twice after the final retrieval relevance fix: sequence 11 returned `grounded`, `cite-027`, and `claimVerification.passed=true`; sequence 12 returned the same rehydrated answer/citation as `cache.mode=exact` in `1.47s`, and its worker interval contained no Agent tool execution or `parallel_executor` call.
- [x] Submit two concurrent chat POSTs for the same meeting and confirm exactly one request is accepted (`200`) while the other receives `409 chat_busy`; the accepted turn completes normally.
- [x] Confirm public chat history reports only sanitized cache fields (`hit`, `mode`, `similarity`) and contains zero raw-thought, full-plan, memory/cache identity, pipeline, token, or internal-error keys.
- [x] Confirm Prometheus has Phase 44 resolver/cache/claim/chat-turn series without meeting-ID labels.

### Acceptance criteria

- [x] Conversation-dependent questions resolve or request clarification before factual retrieval.
- [x] History and memory cannot become evidence, and unsupported claims cannot remain `grounded`.
- [x] Cache and memory cannot cross owner, meeting, generation, context, or pipeline contracts.
- [x] Public chat DTOs do not expose raw reasoning or internal orchestration identifiers.
- [x] Redis, embedding, LLM, broker, and worker-redelivery failures retain durable work or fall back safely according to the owning layer.
- [x] Warm exact-repeat hit rate is 100% for the runtime acceptance question, with rehydrated citations and no second Agent invocation.

## Implementation notes

- Phase 41-43 remain `Done` as historical feature milestones. Phase 44 owns the integrated runtime contract and supersedes their earlier orchestration details.
- History is now used to resolve the canonical question and is not replayed as factual synthesis context. This is stricter than the original Phase 44 draft and removes a stale-history evidence path.
- Semantic direct serving is deliberately not enabled. Shadow precision evidence must meet the 99% gate before a separate controlled canary change.
- The exact-repeat, citation-rehydration, public-sanitization, and serialized-turn runtime gates are recorded above; Phase 44 is complete while semantic direct serving remains an intentionally gated future rollout.

---

## Completion Report

> **Completed at:** 2026-07-15
> **Verified by:** Full backend/frontend suites, dedicated Redis integration tests, Alembic head/autogenerate checks, v2 cutover verification, Compose configuration/startup-log inspection, image builds, healthy deployed services, and meeting-scoped runtime acceptance evidence.

### What was implemented

- Durable serialized chat turns and authoritative retrieval snapshots; canonical conversation resolution; current-snapshot claim grounding; three-layer cache v2; verified strategy-only Agent Memory v2; revisioned three-state feedback; sanitized public API/SSE contracts; and bounded observability/runtime configuration.
- A final independent audit hardened directional claim verification, reference-word disambiguation, embedding-identity fences, memory rebuild lifecycle, exact-cache feedback lineage, singleflight coordination, SSE DTO validation, feedback/history race handling, and visible workspace status/error feedback.
- A follow-up resolver audit removed finite-list-only dependency gating when history exists and made canonical rewriting backend-owned exact substitution, preventing unrecognized pronouns from sharing an empty contextual cache key and preventing provider actor/target reversal.
- The authenticated App Shell now owns one accessible top-center toast surface shared by Meeting and Admin routes; meeting lifecycle notices survive selection changes, clarification remains in the persisted chat thread, and Admin only announces explicit Refresh results.

### What was changed from original plan

- Conversation history resolves the canonical question but is not replayed as synthesis evidence, which is stricter than the draft design.
- Semantic serving remains in `shadow` with canary `0%`; its implementation and kill switch are complete, but promotion intentionally remains gated on offline precision `>=99%`.
- PostgreSQL chat-turn serialization is the correctness boundary; Redis singleflight is a bounded duplicate-work optimization and remains fail-open.

### Notes for future sessions

- Extend semantic temporal hard-negative coverage (for example relative weeks, quarters, and before/after ranges) before collecting promotion evidence; do not enable direct semantic serving until the precision gate is independently demonstrated.
- Keep resolver, verifier, planner, tool, model, guardrail, and schema contract changes inside the pipeline fingerprint so old cache entries are logically invalidated.
- The containerized Celery worker still emits its existing root-user warning; changing its runtime UID is separate infrastructure hardening and not part of Phase 44 behavior.

### Related docs updated

- [x] `docs/explanations/backend-explanation.md`
- [x] `docs/explanations/frontend-explanation.md`
- [x] `docs/explanations/worker-explanation.md`
- [x] `docs/explanations/infrastructure-explanation.md`
- [x] `docs/plans/0 - project overview.md` (Phase 44 remains `Done`)
